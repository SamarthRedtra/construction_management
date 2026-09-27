<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { call, uploadFile } from "@/api"
import { toast, toastError } from "@/toast"
import { debounce, session } from "@/utils"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"

const ctx = computed(() => session.context)
const rows = ref([])
const total = ref(0)
const search = ref("")
const typeFilter = ref("")
const loading = ref(false)
const creating = ref(false)
const saving = ref(false)
const importState = ref(null)
const fileInput = ref(null)
const emptyItem = { item_type: "Stockable", item_name: "", item_code: "", item_group: "", asset_category: "", expense_account: "" }
const itemForm = reactive({ company: ctx.value.default_company || "", ...emptyItem })

const visibleRows = computed(() => (typeFilter.value ? rows.value.filter((row) => row.controlled_item_type === typeFilter.value) : rows.value))

async function load(append = false) {
	loading.value = true
	try {
		const result = await call("get_catalog", { search: search.value, start: append ? rows.value.length : 0, page_length: 50 })
		rows.value = append ? [...rows.value, ...result.rows] : result.rows
		total.value = result.total_count
	} finally {
		loading.value = false
	}
}

async function createItem() {
	saving.value = true
	try {
		const result = await call("create_controlled_item", { data: itemForm })
		toast(`Controlled item ${result.name} created`)
		Object.assign(itemForm, emptyItem)
		creating.value = false
		load()
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

async function onWorkbookChosen(event) {
	const file = event.target.files?.[0]
	event.target.value = ""
	if (!file) return
	importState.value = { stage: "uploading", file: file.name }
	try {
		const uploaded = await uploadFile(file)
		const preview = await call("preview_catalog_workbook", { file_url: uploaded.file_url })
		importState.value = { stage: "preview", file: file.name, file_url: uploaded.file_url, preview }
	} catch (error) {
		importState.value = null
		toastError(error)
	}
}

async function confirmImport() {
	const { file_url } = importState.value
	importState.value = { ...importState.value, stage: "importing" }
	try {
		const result = await call("import_catalog_workbook", { file_url })
		toast(`Catalog imported: ${result.created} created, ${result.reused} reused`)
		importState.value = null
		load()
	} catch (error) {
		importState.value = { ...importState.value, stage: "preview" }
		toastError(error)
	}
}

watch(search, debounce(() => load(), 300))
onMounted(() => load())
</script>

<template>
	<PageHeader title="Controlled Catalog" subtitle="Approved Nos items that can be ordered, received and transferred." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Controlled Catalog' }]">
		<template v-if="ctx.can_manage_catalog" #actions>
			<button class="cp-btn" @click="fileInput.click()">Import workbook</button>
			<button class="cp-btn primary" @click="creating = true">New controlled item</button>
			<input ref="fileInput" type="file" accept=".xlsx" hidden @change="onWorkbookChosen" />
		</template>
	</PageHeader>

	<div class="cp-filters">
		<input v-model="search" class="cp-input cp-search" placeholder="Search approved catalog by description" autofocus />
		<div class="cp-segmented">
			<button :class="{ active: !typeFilter }" @click="typeFilter = ''">All</button>
			<button v-for="type in ['Stockable', 'Asset', 'Service']" :key="type" :class="{ active: typeFilter === type }" @click="typeFilter = type">{{ type }}</button>
		</div>
	</div>

	<section class="cp-card">
		<table class="cp-table">
			<thead><tr><th>Description</th><th>Group</th><th>Type</th><th>Source</th><th>UOM</th></tr></thead>
			<tbody>
				<tr v-for="item in visibleRows" :key="item.name">
					<td><strong>{{ item.item_name }}</strong><small>{{ item.name }}</small></td>
					<td>{{ item.item_group }}</td>
					<td><span class="cp-pill info">{{ item.controlled_item_type }}</span></td>
					<td><span class="cp-muted">{{ item.controlled_catalog_source || "—" }}</span></td>
					<td>{{ item.stock_uom }}</td>
				</tr>
				<tr v-if="!loading && !visibleRows.length"><td colspan="5" class="cp-empty-row">No approved items found.</td></tr>
			</tbody>
		</table>
		<footer v-if="rows.length" class="cp-card-foot">
			<span>{{ rows.length }} of {{ total }} items</span>
			<button v-if="rows.length < total" class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button>
		</footer>
	</section>

	<Modal v-if="creating" title="New controlled item" wide @close="creating = false">
		<form id="cp-item-form" class="cp-stack" @submit.prevent="createItem">
			<div class="cp-grid-2">
				<LinkSelect v-model="itemForm.company" doctype="Company" label="Company" :required="true" />
				<label class="cp-field">
					<span>Item type<i>*</i></span>
					<select v-model="itemForm.item_type" class="cp-input"><option>Stockable</option><option>Asset</option><option>Service</option></select>
				</label>
				<label class="cp-field"><span>Description<i>*</i></span><input v-model="itemForm.item_name" class="cp-input" required /></label>
				<label class="cp-field"><span>Item code</span><input v-model="itemForm.item_code" class="cp-input" placeholder="Auto-generated if empty" /></label>
				<LinkSelect v-model="itemForm.item_group" doctype="Item Group" label="Item group" :required="true" :filters="{ is_group: 0 }" />
				<LinkSelect v-if="itemForm.item_type === 'Asset'" v-model="itemForm.asset_category" doctype="Asset Category" label="Asset category" placeholder="Company default" />
				<LinkSelect v-if="itemForm.item_type === 'Service'" v-model="itemForm.expense_account" doctype="Account" label="Service expense account" placeholder="Company default" :filters="{ company: itemForm.company, is_group: 0 }" />
			</div>
			<p class="cp-hint">Controlled items always use UOM Nos.</p>
		</form>
		<template #footer>
			<button class="cp-btn" @click="creating = false">Cancel</button>
			<button type="submit" form="cp-item-form" class="cp-btn primary" :disabled="saving">{{ saving ? "Creating…" : "Create item" }}</button>
		</template>
	</Modal>

	<Modal v-if="importState" title="Import catalog workbook" @close="importState.stage === 'preview' && (importState = null)">
		<p v-if="importState.stage === 'uploading'" class="cp-muted">Uploading and checking {{ importState.file }}…</p>
		<p v-else-if="importState.stage === 'importing'" class="cp-muted">Importing {{ importState.file }}…</p>
		<template v-else>
			<p><strong>{{ importState.file }}</strong></p>
			<div class="cp-stats compact">
				<div class="cp-stat static"><small>Valid rows</small><strong>{{ importState.preview.valid_rows }}</strong></div>
				<div class="cp-stat static"><small>New items</small><strong>{{ importState.preview.create }}</strong></div>
				<div class="cp-stat static"><small>Existing reused</small><strong>{{ importState.preview.reuse }}</strong></div>
			</div>
			<div v-if="importState.preview.supplier_exceptions.length" class="cp-exceptions">
				<strong>{{ importState.preview.supplier_exceptions.length }} exceptions</strong>
				<ul>
					<li v-for="row in importState.preview.supplier_exceptions.slice(0, 20)" :key="`${row.row}-${row.reason}`">Row {{ row.row }}<template v-if="row.item"> · {{ row.item }}</template>: {{ row.reason }}</li>
				</ul>
			</div>
		</template>
		<template v-if="importState.stage === 'preview'" #footer>
			<button class="cp-btn" @click="importState = null">Cancel</button>
			<button class="cp-btn primary" @click="confirmImport">Import</button>
		</template>
	</Modal>
</template>
