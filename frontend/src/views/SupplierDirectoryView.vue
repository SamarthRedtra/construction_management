<script setup>
import { onMounted, ref, watch } from "vue"
import { call } from "@/api"
import { toastError } from "@/toast"
import { debounce } from "@/utils"
import PageHeader from "@/components/PageHeader.vue"
import SupplierDialog from "@/components/SupplierDialog.vue"

const search = ref("")
const rows = ref([])
const loading = ref(false)
const editing = ref("")

async function load() {
	loading.value = true
	try {
		rows.value = await call("get_procurement_suppliers", { search: search.value })
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
}

function saved() {
	editing.value = ""
	load()
}

watch(search, debounce(load, 250))
onMounted(load)
</script>

<template>
	<PageHeader title="Suppliers" subtitle="Procurement supplier directory, payment terms, contacts and addresses." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Suppliers' }]">
		<template #actions><button class="cp-btn primary" @click="editing = 'new'">New supplier</button></template>
	</PageHeader>
	<section class="cp-section"><input v-model="search" class="cp-input cp-search" placeholder="Search supplier, tax ID or group" /></section>
	<section class="cp-card"><table class="cp-table"><thead><tr><th>Supplier</th><th>Group</th><th>Type</th><th>Tax ID</th><th>Payment terms</th><th /></tr></thead><tbody>
		<tr v-for="row in rows" :key="row.name"><td><strong>{{ row.supplier_name }}</strong><small>{{ row.name }}</small></td><td>{{ row.supplier_group || '—' }}</td><td>{{ row.supplier_type || '—' }}</td><td>{{ row.tax_id || '—' }}</td><td>{{ row.payment_terms || '—' }}</td><td><button class="cp-btn sm" @click="editing = row.name">Edit</button></td></tr>
		<tr v-if="!loading && !rows.length"><td colspan="6" class="cp-empty-row">No suppliers found.</td></tr>
	</tbody></table></section>
	<SupplierDialog v-if="editing" :supplier="editing === 'new' ? '' : editing" @close="editing = ''" @saved="saved" />
</template>
