<template>
  <section class="page" data-module="monitor">
    <header class="page-head">
      <div>
        <h2>采集监控管理</h2>
        <p class="page-desc">维护采集监控指标的输入、执行约束与结果记录，为采集监控提供可验证的数据工程流程。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记监控指标</button>
        <button class="btn" type="button" @click="exportRows">导出采集监控清单</button>
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
          <td :colspan="columns.length + 1" class="empty-state">暂无采集监控数据，可先登记监控指标</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条采集监控记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <section class="hit-view">
      <header class="page-head">
        <div>
          <h3>缓存命中视图</h3>
          <p class="page-desc">与运营概览、缓存命中看板同源：各版本占比、批次看板与失效记录均来自真实缓存条目，异常刷新已落入上方待处理区。</p>
        </div>
        <div class="page-actions">
          <button class="btn" type="button" @click="reloadHitView">刷新视图</button>
        </div>
      </header>

      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">命中总量</span>
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

      <h4 class="board-title">各版本占比</h4>
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

      <h4 class="board-title">批次看板（按缓存键模板归并）</h4>
      <table class="data-table">
        <thead>
          <tr><th>缓存键模板</th><th>条目数</th><th>命中次数</th><th>失效次数</th><th>版本分布</th></tr>
        </thead>
        <tbody>
          <tr v-for="batch in hitBoard.批次看板 ?? []" :key="batch.缓存键模板">
            <td>{{ batch.缓存键模板 }}</td>
            <td>{{ batch.条目数 }}</td>
            <td>{{ batch.命中次数 }}</td>
            <td>{{ batch.失效次数 }}</td>
            <td>{{ formatVersionSpread(batch.版本分布) }}</td>
          </tr>
          <tr v-if="!(hitBoard.批次看板 ?? []).length">
            <td colspan="5" class="empty-state">暂无批次数据</td>
          </tr>
        </tbody>
      </table>

      <h4 class="board-title">失效记录</h4>
      <table class="data-table">
        <thead>
          <tr><th>记录编号</th><th>缓存键模板</th><th>缓存键</th><th>失效次数</th><th>最近失效原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in hitBoard.失效记录 ?? []" :key="String(item.记录编号)">
            <td>{{ item.记录编号 }}</td>
            <td>{{ item.缓存键模板 }}</td>
            <td>{{ item.缓存键 }}</td>
            <td>{{ item.失效次数 }}</td>
            <td>{{ item.最近失效原因 }}</td>
          </tr>
          <tr v-if="!(hitBoard.失效记录 ?? []).length">
            <td colspan="5" class="empty-state">暂无失效记录</td>
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

const ENDPOINT = '/api/monitor'
const columns = ["指标编号", "关联端点", "成功率阈值", "延迟阈值", "错误率告警", "检测频率", "通知渠道", "静默分钟"]
const actions = ["提交校验", "启用监控", "停用监控"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const stats = [{"label": "监控指标总数", "value": 0}, {"label": "已启用指标", "value": 0}, {"label": "待校验指标", "value": 0}]

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
  批次看板?: { 缓存键模板: string; 条目数: number; 命中次数: number; 失效次数: number; 版本分布: Record<string, number> }[]
  失效记录?: { 记录编号: string; 缓存键模板: string; 缓存键: string; 失效次数: number; 最近失效原因: string }[]
}

const hitBoard = ref<HitBoard>({})

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatVersionSpread(spread: Record<string, number>) {
  return Object.entries(spread).map(([version, count]) => `${version}×${count}`).join('、')
}

async function reloadHitView() {
  try {
    hitBoard.value = await fetchJson<HitBoard>('/api/cachehit/dashboard')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '缓存命中视图读取失败'
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
  errorMessage.value = '监控指标登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('采集监控动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集监控操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('监控指标列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '采集监控列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadHitView()
})
</script>

<style scoped>
.hit-view { margin-top: 24px; border-top: 1px solid var(--border); padding-top: 8px; }
.board-title { margin: 16px 0 8px; font-size: 14px; }
</style>
