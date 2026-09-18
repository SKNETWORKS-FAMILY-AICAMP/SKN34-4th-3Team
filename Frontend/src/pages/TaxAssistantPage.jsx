import React from 'react';
import { TAX_RULES, TAX_CHIPS, DEFAULT_BIZ, DEFAULT_REGION } from '../constants.js';
import { AiConsult } from '../components/AiConsult.jsx';

export function TaxAssistantPage({ user, onRequireLogin }) {
  return (
    <AiConsult
      user={user || { biz: DEFAULT_BIZ, region: DEFAULT_REGION }}
      rules={TAX_RULES}
      suggestions={TAX_CHIPS}
      title="AI 세무 Assistant"
      category="tax"
      onRequireLogin={onRequireLogin}
      compact
      withSidebar
    />
  );
}

/* ===== 지원사업 공고문 AI 분석·구조화 ===== */
