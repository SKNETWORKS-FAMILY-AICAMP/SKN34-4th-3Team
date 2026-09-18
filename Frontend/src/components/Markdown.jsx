import React from 'react';

export function mdInline(text, keyPrefix) {
  const out = [];
  // **굵게** | *기울임* | `코드` 를 한 번에 훑는다
  const re = /(\*\*[^*]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    const k = `${keyPrefix}-i${i++}`;
    if (t.startsWith('**')) out.push(<strong key={k}>{t.slice(2, -2)}</strong>);
    else if (t.startsWith('`')) out.push(<code key={k} className="md-code">{t.slice(1, -1)}</code>);
    else out.push(<em key={k}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }) {
  const lines = String(text || '').split('\n');
  const blocks = [];
  let list = null; // { ordered, items: [] }

  const flushList = () => {
    if (!list) return;
    const Tag = list.ordered ? 'ol' : 'ul';
    blocks.push(
      <Tag key={`l${blocks.length}`} className="md-list">
        {list.items.map((it, i) => <li key={i}>{mdInline(it, `l${blocks.length}-${i}`)}</li>)}
      </Tag>
    );
    list = null;
  };

  lines.forEach((raw, idx) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const num = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const head = line.match(/^(#{1,4})\s+(.*)$/);

    if (bullet) {
      if (!list || list.ordered) { flushList(); list = { ordered: false, items: [] }; }
      list.items.push(bullet[1]);
      return;
    }
    if (num) {
      if (!list || !list.ordered) { flushList(); list = { ordered: true, items: [] }; }
      list.items.push(num[1]);
      return;
    }
    flushList();
    if (!line.trim()) return; // 빈 줄은 문단 구분
    if (head) {
      blocks.push(<p key={`h${idx}`} className="md-head">{mdInline(head[2], `h${idx}`)}</p>);
      return;
    }
    if (/^\s*>\s?/.test(line)) {
      blocks.push(<p key={`q${idx}`} className="md-quote">{mdInline(line.replace(/^\s*>\s?/, ''), `q${idx}`)}</p>);
      return;
    }
    blocks.push(<p key={`p${idx}`} className="md-p">{mdInline(line, `p${idx}`)}</p>);
  });
  flushList();
  return <React.Fragment>{blocks}</React.Fragment>;
}
