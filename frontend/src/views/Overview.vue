<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常。</p>
      </div>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>
    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>

    <section class="hit-summary">
      <h3>缓存命中真实记录</h3>
      <p class="page-desc">来自缓存命中数据集的真实条目累计，不随页面刷新或重复点击变化。</p>
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">命中总量</span>
          <strong class="stat-value">{{ cacheHit.命中总量 ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">失效总量</span>
          <strong class="stat-value">{{ cacheHit.失效总量 ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">异常缓存条目</span>
          <strong class="stat-value">{{ cacheHit.异常条目 ?? 0 }}</strong>
        </article>
      </div>
      <table class="data-table">
        <thead>
          <tr><th>可见版本</th><th>条目数</th><th>命中次数</th><th>命中占比</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in cacheHit.各版本占比 ?? []" :key="item.版本">
            <td>{{ item.版本 }}</td>
            <td>{{ item.条目数 }}</td>
            <td>{{ item.命中次数 }}</td>
            <td>{{ (item.占比 * 100).toFixed(1) }}%</td>
          </tr>
          <tr v-if="!(cacheHit.各版本占比 ?? []).length">
            <td colspan="4" class="empty-state">暂无缓存命中记录</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  cachehit?: {
    命中总量: number
    失效总量: number
    异常条目: number
    各版本占比: { 版本: string; 条目数: number; 命中次数: number; 占比: number }[]
  }
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const cacheHit = ref<NonNullable<Overview['cachehit']>>({ 命中总量: 0, 失效总量: 0, 异常条目: 0, 各版本占比: [] })

onMounted(async () => {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    if (payload.cachehit) {
      cacheHit.value = payload.cachehit
    }
  } catch {
    cards.value = [{"label": "业务模块", "value": 0}, {"label": "今日新增", "value": 0}]
    moduleRows.value = [{"name": "接口管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "接口编排", "created": 0, "pending": 0, "abnormal": 0}, {"name": "频率控制", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据映射", "created": 0, "pending": 0, "abnormal": 0}, {"name": "响应校验", "created": 0, "pending": 0, "abnormal": 0}, {"name": "失败重试", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据聚合", "created": 0, "pending": 0, "abnormal": 0}, {"name": "凭证管理", "created": 0, "pending": 0, "abnormal": 0}, {"name": "缓存策略", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据转储", "created": 0, "pending": 0, "abnormal": 0}, {"name": "采集调度", "created": 0, "pending": 0, "abnormal": 0}, {"name": "采集监控", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据转换", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据清洗", "created": 0, "pending": 0, "abnormal": 0}, {"name": "限流配置", "created": 0, "pending": 0, "abnormal": 0}, {"name": "采集日志", "created": 0, "pending": 0, "abnormal": 0}, {"name": "增量采集", "created": 0, "pending": 0, "abnormal": 0}, {"name": "数据导出", "created": 0, "pending": 0, "abnormal": 0}]
  }
})
</script>

<style scoped>
.hit-summary { margin-top: 24px; border-top: 1px solid var(--border); padding-top: 8px; }
</style>
