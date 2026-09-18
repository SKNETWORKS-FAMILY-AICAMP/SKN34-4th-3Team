<!-- 전→후 수치 타일 (Frontend 09-metrics-closing.css .metric) -->
<script setup lang="ts">
defineProps<{
  label: string
  after: string
  before?: string
  delta?: string
  note?: string
}>()
</script>

<template>
  <div class="card metric">
    <span class="metric__label">{{ label }}</span>
    <b class="metric__value num">{{ after }}</b>
    <span v-if="before" class="metric__before num">{{ before }} →</span>
    <span v-if="delta" class="metric__delta num">{{ delta }}</span>
    <span v-if="note" class="metric__note">{{ note }}</span>
  </div>
</template>

<style scoped>
.metric {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric__label {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-soft);
}
.metric__value {
  order: 2;
  font-size: 50px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.03em;
  color: var(--ink);
}
.metric__before {
  order: 1;
  margin-top: 6px;
  font-size: 15px;
  color: var(--ink-faint);
}
.metric__delta {
  order: 3;
  font-size: 16px;
  font-weight: 700;
  color: var(--green);
}
.metric__note {
  order: 4;
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-faint);
}
</style>
