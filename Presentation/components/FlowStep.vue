<!-- 단계 카드 (Frontend 05-roadmap.css .rz__step, 아이콘은 roadmapIcons.jsx와 같은 선 스타일) -->
<script setup lang="ts">
defineProps<{
  icon: string
  title: string
  phase?: string
  desc?: string
  accent?: boolean
}>()

const paths: Record<string, string> = {
  A: 'M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.4c.6.5 1 1.4 1 2.6h6c0-1.2.4-2.1 1-2.6A6 6 0 0 0 12 3Z',
  B: 'M7 3h8l3 3v15H7zM15 3v4h4M10 12h5M10 16h5',
  C: 'M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 0 1 0-17ZM8.5 12l2.5 2.5 4.5-5',
  D: 'M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 0 1 0-17ZM12 7.5v9M9.7 9.7c0-1 1-1.6 2.3-1.6s2.3.6 2.3 1.6-1 1.3-2.3 1.5-2.3.6-2.3 1.6 1 1.6 2.3 1.6 2.3-.6 2.3-1.6',
  E: 'm7.5 16.5 9-9M8.5 6.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4ZM15.5 13.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4Z',
  F: 'M7 3.5h10v17l-2.5-1.6-2.5 1.6-2.5-1.6L7 20.5zM10 8h4M10 12h4',
  Z: 'm4 15 5-5 3 3 8-8M16 5h4v4',
  user: 'M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8ZM4.5 20c1.2-3.4 4-5 7.5-5s6.3 1.6 7.5 5',
  profile: 'M4 5h16v14H4zM8 10a2 2 0 1 0 4 0 2 2 0 0 0-4 0M7 16c.6-1.4 1.7-2 3-2s2.4.6 3 2M15 10h3M15 13h3',
  spark: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18',
  search: 'M10.5 4a6.5 6.5 0 1 1 0 13 6.5 6.5 0 0 1 0-13ZM15.5 15.5 20 20',
  chat: 'M4 5h16v11H9l-5 4zM8 9.5h8M8 12.5h5',
}
</script>

<template>
  <div class="fstep" :class="{ 'fstep--accent': accent }">
    <span class="fstep__ico">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path :d="paths[icon] || paths.A" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </span>
    <span v-if="phase" class="fstep__phase">{{ phase }}</span>
    <span class="fstep__t">{{ title }}</span>
    <span v-if="desc" class="fstep__d">{{ desc }}</span>
  </div>
</template>

<style scoped>
.fstep {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
.fstep__ico {
  display: grid;
  place-items: center;
  width: 72px;
  height: 72px;
  border-radius: 22px;
  background: var(--surface-solid);
  border: 1px solid var(--line-strong);
  color: var(--blue-deep);
  box-shadow: var(--shadow-sm);
}
.fstep__ico svg {
  width: 32px;
  height: 32px;
}
.fstep--accent .fstep__ico {
  background: var(--brand);
  border-color: transparent;
  color: #fff;
}
.fstep__phase {
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--blue);
}
.fstep__t {
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--ink);
}
.fstep__d {
  max-width: 22ch;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ink-soft);
}
</style>
