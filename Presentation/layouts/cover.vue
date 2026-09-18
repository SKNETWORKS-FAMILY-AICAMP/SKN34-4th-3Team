<!-- 표지·마무리 레이아웃: Frontend hero의 blue/violet 글로우 배경 -->
<template>
  <div class="slidev-layout cover-slide">
    <div class="glow glow--blue" aria-hidden="true" />
    <div class="glow glow--violet" aria-hidden="true" />
    <div class="cover-slide__inner">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.cover-slide {
  display: flex;
  flex-direction: row;
  align-items: center;
  overflow: hidden;
  background: var(--ground);
}
.cover-slide__inner {
  position: relative;
  z-index: 1;
  width: 100%;
}
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(14px);
  pointer-events: none;
}
.glow--blue {
  top: -200px;
  right: -140px;
  width: 720px;
  height: 560px;
  background: radial-gradient(circle, var(--glow-blue), transparent 66%);
}
.glow--violet {
  bottom: -300px;
  left: -160px;
  width: 700px;
  height: 580px;
  background: radial-gradient(circle, var(--glow-violet), transparent 66%);
}
</style>
