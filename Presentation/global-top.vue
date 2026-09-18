<!-- 하단 브랜드마크 + 이전/다음 버튼 + 페이지 번호 (표지에서는 브랜드마크 숨김) -->
<script setup lang="ts">
import { useNav } from '@slidev/client'
import { slideScale } from '@slidev/client/state/index.ts'

const { currentPage, currentLayout, total, hasPrev, hasNext, prev, next } = useNav()

// 설정 메뉴를 숨겼으므로 이전에 바꾼 배율이 남지 않도록 자동 맞춤으로 고정
slideScale.value = 0
</script>

<template>
  <footer class="deck-foot">
    <span v-if="currentLayout !== 'cover'" class="deck-foot__brand"><span class="brandmark">ON</span>창업ON</span>
    <span v-else />
    <nav class="deck-nav" aria-label="슬라이드 이동">
      <button type="button" aria-label="이전 슬라이드" :disabled="!hasPrev" @click="prev()">‹</button>
      <span class="num">{{ currentPage }} / {{ total }}</span>
      <button type="button" aria-label="다음 슬라이드" :disabled="!hasNext" @click="next()">›</button>
    </nav>
  </footer>
</template>

<style scoped>
.deck-foot {
  position: absolute;
  left: 72px;
  right: 72px;
  bottom: 14px;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: var(--ink-faint);
}
.deck-foot__brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  color: var(--ink-soft);
}
.deck-foot .brandmark {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  font-size: 8px;
}
.deck-nav {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.deck-nav button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 0 0 2px;
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--ink-soft);
  font-size: 17px;
  line-height: 1;
  cursor: pointer;
}
.deck-nav button:hover:not(:disabled) {
  border-color: var(--blue);
  color: var(--blue-deep);
}
.deck-nav button:disabled {
  opacity: 0.35;
  cursor: default;
}
</style>
