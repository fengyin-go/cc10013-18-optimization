<template>
  <section class="page" data-module="cache">
    <header class="page-head">
      <div>
        <h2>缓存策略管理</h2>
        <p class="page-desc">维护缓存策略的输入、执行约束与结果记录，为响应缓存提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记缓存规则</button>
        <button class="btn" type="button" @click="exportRows">导出缓存策略清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无缓存策略数据，可先登记缓存规则</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条缓存策略记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="hit-section">
      <header class="page-head">
        <div>
          <h3>缓存命中数据集</h3>
          <p class="page-desc">按缓存键模板归并的真实缓存条目：同一缓存键只暴露一个可见刷新结果，命中量按条目累计，读取不随重复点击变化。</p>
        </div>
        <div class="page-actions">
          <button class="btn" type="button" @click="reloadHits">刷新读取</button>
        </div>
      </header>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">命中总量（真实条目累计）</span>
          <strong class="stat-value">{{ hitBoard.命中总量 ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">失效总量</span>
          <strong class="stat-value">{{ hitBoard.失效总量 ?? 0 }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">异常条目</span>
          <strong class="stat-value">{{ hitBoard.异常条目 ?? 0 }}</strong>
        </article>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in hitColumns" :key="column">{{ column }}</th>
            <th>回源动作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in hitRows" :key="String(row.id)">
            <td v-for="column in hitColumns" :key="column">{{ formatHitCell(column, row) }}</td>
            <td class="row-actions">
              <button class="link" type="button" @click="recordHit(row)">记录命中</button>
              <button class="link" type="button" @click="hitAction('refresh', row)">开始刷新</button>
              <button class="link" type="button" @click="hitAction('complete', row)">完成刷新</button>
              <button class="link" type="button" @click="hitAction('bump-version', row)">换版</button>
              <button class="link" type="button" @click="hitAction('invalidate', row)">失效</button>
            </td>
          </tr>
          <tr v-if="!hitRows.length">
            <td :colspan="hitColumns.length + 1" class="empty-state">暂无缓存命中记录</td>
          </tr>
        </tbody>
      </table>

      <h4 class="board-title">缓存命中看板 · 各版本占比</h4>
      <table class="data-table">
        <thead>
          <tr><th>可见版本</th><th>条目数</th><th>命中次数</th><th>命中占比</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in hitBoard.各版本占比 ?? []" :key="item.版本">
            <td>{{ item.版本 }}</td>
            <td>{{ item.条目数 }}</td>
            <td>{{ item.命中次数 }}</td>
            <td>{{ formatPercent(item.占比) }}</td>
          </tr>
          <tr v-if="!(hitBoard.各版本占比 ?? []).length">
            <td colspan="4" class="empty-state">暂无版本占比数据</td>
          </tr>
        </tbody>
      </table>
    </section>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson, request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/cache'
const columns = ["规则编号", "关联端点", "缓存键模板", "过期秒数", "预热开关", "淘汰策略", "命中率阈值", "最大条目"]
const actions = ["提交校验", "启用缓存", "停用缓存"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const stats = [{"label": "缓存规则总数", "value": 0}, {"label": "已启用规则", "value": 0}, {"label": "待校验规则", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

type HitBoard = {
  命中总量?: number
  失效总量?: number
  异常条目?: number
  各版本占比?: { 版本: string; 条目数: number; 命中次数: number; 占比: number }[]
}

const HIT_ENDPOINT = '/api/cachehit'
const hitColumns = ["记录编号", "缓存键模板", "缓存键", "映射版本", "可见版本", "刷新状态", "命中次数", "失效次数"]
const hitRows = ref<Row[]>([])
const hitBoard = ref<HitBoard>({})

function formatHitCell(column: string, row: Row) {
  const value = row[column]
  if (value === null || value === undefined || value === '') return '—'
  if (column === '映射版本' || column === '可见版本') return `v${value}`
  return value
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

async function reloadHits() {
  try {
    const [listPayload, boardPayload] = await Promise.all([
      fetchJson<{ items: Row[] }>(`${HIT_ENDPOINT}?size=200`),
      fetchJson<HitBoard>(`${HIT_ENDPOINT}/dashboard`),
    ])
    hitRows.value = listPayload.items ?? []
    hitBoard.value = boardPayload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缓存命中数据集读取失败'
  }
}

async function recordHit(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${HIT_ENDPOINT}/hit`, {
      method: 'POST',
      body: JSON.stringify({ values: { 缓存键模板: row['缓存键模板'], 缓存键: row['缓存键'], 关联端点: row['关联端点'] } }),
    })
    if (!response.ok) throw new Error('命中登记未生效，请稍后重试')
    await reloadHits()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '命中登记失败'
  }
}

async function hitAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${HIT_ENDPOINT}/${row.id}/${action}`, { method: 'POST' })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '缓存命中动作未生效')
    }
    await reloadHits()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缓存命中操作失败'
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '缓存规则登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('缓存策略动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缓存策略操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('缓存规则列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缓存策略列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadHits()
})
</script>

<style scoped>
.hit-section { margin-top: 24px; border-top: 1px solid var(--border); padding-top: 8px; }
.board-title { margin: 16px 0 8px; font-size: 14px; }
</style>
