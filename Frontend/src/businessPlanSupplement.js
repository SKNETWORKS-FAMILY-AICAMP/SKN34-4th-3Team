export function paginateSupplementFields(fields, limit = 570) {
  const groups = [];
  for (const field of fields) {
    const section = field.section_id || field.field_id;
    const previous = groups[groups.length - 1];
    if (previous?.section === section) previous.fields.push(field);
    else groups.push({ section, fields: [field] });
  }
  const height = (field) => 95 + 76 * Math.max(1,
    (field.missing_fields?.length || field.required_information?.length || 1))
    + (field.type === 'table' ? 70 : 0);
  const pages = [];
  let current = [];
  let used = 0;
  const append = (items) => {
    const size = items.reduce((sum, field) => sum + height(field), 0);
    if (current.length && used + size > limit) {
      pages.push(current);
      current = [];
      used = 0;
    }
    current.push(...items);
    used += size;
  };
  for (const group of groups) {
    const size = group.fields.reduce((sum, field) => sum + height(field), 0);
    if (size <= limit) append(group.fields);
    else group.fields.forEach((field) => append([field]));
  }
  if (current.length) pages.push(current);
  return pages;
}

export function reassessSupplementFields(fields, answers, choices, images = {}) {
  return fields.map((field) => {
    if (field.type === 'image') {
      if (choices[field.field_id] === 'not_applicable') {
        return { ...field, status: 'not_applicable', missing_fields: [], missing_reason: '' };
      }
      return images[field.field_id] && choices[field.field_id] !== 'no_information'
        ? { ...field, status: 'ready', missing_fields: [], missing_reason: '' }
        : { ...field, status: 'missing', missing_fields: ['이미지 파일'] };
    }
    if (!['missing', 'partial'].includes(field.status)) return field;
    if (choices[field.field_id] === 'not_applicable') {
      return { ...field, status: 'not_applicable', missing_fields: [], missing_reason: '' };
    }
    if (choices[field.field_id] === 'no_information') return field;
    const required = field.missing_fields?.length ? field.missing_fields : field.required_information || [];
    const missing = required.filter((item) => !answers[`${field.field_id}:${item}`]?.trim());
    if (!missing.length && required.length) {
      return { ...field, status: 'ready', missing_fields: [], missing_reason: '' };
    }
    const supplied = required.some((item) => answers[`${field.field_id}:${item}`]?.trim());
    return { ...field, status: supplied || field.status === 'partial' ? 'partial' : 'missing',
      missing_fields: missing };
  });
}

export function templateContext(fields, answers, choices = {}, editedKeys = []) {
  const details = fields.map((field) => {
    const choice = choices[field.field_id];
    const supplied = Object.fromEntries((field.required_information || []).map((item) =>
      [item, choice === 'no_information' || choice === 'not_applicable'
        ? '' : answers[`${field.field_id}:${item}`]?.trim() || ''])
      .filter(([, value]) => value || choice === 'no_information'));
    return {
      id: field.field_id,
      status: field.status,
      ...(['table', 'image'].includes(field.type) ? { type: field.type } : {}),
      ...(field.status !== 'ready' && field.instruction ? { instruction: field.instruction } : {}),
      ...(field.missing_fields?.length ? { missing: field.missing_fields } : {}),
      ...(field.mapped_information?.length ? { mapped: field.mapped_information } : {}),
      ...(Object.keys(supplied).length ? { answers: supplied } : {}),
      ...(choice ? { choice } : {}),
    };
  });
  return '__FIELD_CONTEXT_V1__\n' + JSON.stringify({ fields: details, editedKeys });
}
