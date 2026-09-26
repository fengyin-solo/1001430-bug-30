<template>
  <section class="page" data-module="light">
    <header class="page-head">
      <div>
        <h2>照明设施管理</h2>
        <p class="page-desc">维护照明设施，围绕设施编号、灯杆编号、灯具类型、所在道路做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记照明设施</button>
        <button class="btn" type="button" @click="exportRows">导出照明设施清单</button>
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
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无照明设施数据，可先登记照明设施</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条照明设施记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/light'
const columns = ["设施编号", "灯杆编号", "灯具类型", "所在道路", "亮灯率", "上次检修日", "责任班组", "设施状态", "检修人", "检修结论", "不合规项"]
const statuses = ["待检修", "检修中", "正常亮灯", "缺亮待修", "已停用"]
// 已停用与检修中的设施不允许再安排检修；只有检修中才能落检修结论。
const ACTION_BY_STATUS: Record<string, string[]> = {
  待检修: ["安排检修", "停用设施"],
  检修中: ["确认正常", "确认异常", "停用设施"],
  正常亮灯: ["安排检修", "停用设施"],
  缺亮待修: ["安排检修", "停用设施"],
  已停用: [],
}

const session = useSessionStore()
const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref([
  { label: '在册照明设施', value: '—' },
  { label: '缺亮待修', value: '—' },
  { label: '平均亮灯率', value: '—' },
])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

function availableActions(row: Row): string[] {
  return ACTION_BY_STATUS[String(row['设施状态'] ?? row.status ?? '')] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '照明设施登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  const values: Record<string, string> = { action }
  if (action === '安排检修') {
    const operator = window.prompt('请填写检修人', session.operator)
    if (operator === null) return
    if (!operator.trim()) {
      errorMessage.value = '安排检修需要填写检修人'
      return
    }
    values['检修人'] = operator.trim()
  }
  if (action === '确认异常') {
    const defect = window.prompt('请写清不合规项（哪一头不合规）')
    if (defect === null) return
    if (!defect.trim()) {
      errorMessage.value = '确认异常需要写清不合规项'
      return
    }
    values['不合规项'] = defect.trim()
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '照明设施动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message ?? '照明设施操作已完成'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '照明设施操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}?${query}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listResponse.ok) {
      throw new Error('照明设施列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const summary = await statsResponse.json()
      stats.value = stats.value.map((item) => ({
        ...item,
        value: String(summary[item.label] ?? '—'),
      }))
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '照明设施列表读取失败'
  }
}

onMounted(reload)
</script>
