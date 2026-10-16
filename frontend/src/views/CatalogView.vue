<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { call, uploadFile } from "@/api"
import { toast, toastError } from "@/toast"
import { debounce, session } from "@/utils"
import CatalogTabs from "@/components/CatalogTabs.vue"
import CatalogOriginChoice from "@/components/CatalogOriginChoice.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"
import PriceHistory from "@/components/PriceHistory.vue"

const ctx = computed(() => session.context)
const rows = ref([])
const total = ref(0)
const search = ref("")
const typeFilter = ref("")
const groupFilter = ref("")
const sourceFilter = ref("")
const stockFilter = ref("")
const sortBy = ref("item_name")
const sortOrder = ref("asc")
const filterOptions = ref({ item_groups: [], sources: [] })
const loading = ref(false)
const exporting = ref("")
let latestLoad = 0
const creating = ref(false)
const saving = ref(false)
const importState = ref(null)
const fileInput = ref(null)
const stockItem = ref(null)
const stockRows = ref([])
const opening = ref(false)
const openingSaving = ref(false)
const mrgSnapshotSaving = ref(false)
const priceItem = ref(null)
const priceContext = ref(null)
const priceSaving = ref(false)
const priceForm = reactive({ company: "", item_code: "", supplier: "", price_list: "Standard Buying", proposed_rate: "", reason: "" })
const selectedItemCodes = ref(new Set())
const supplierLinking = ref(false)
const supplierLinkSaving = ref(false)
const supplierLinkForm = reactive({ company: ctx.value.default_company || "", supplier: "" })
const groupChanging = ref(false)
const groupChangeSaving = ref(false)
const groupChangeForm = reactive({ company: ctx.value.default_company || "", item_group: "" })
const editingItem = ref(false)
const itemEditSaving = ref(false)
const itemEditForm = reactive({ company: ctx.value.default_company || "", item_code: "", item_name: "", item_group: "", item_type: "Stockable", stock_uom: "Nos", supplier: "", rate: 0, asset_category: "", expense_account: "" })
const emptyItem = { item_type: "Stockable", item_name: "", item_code: "", item_group: "", stock_uom: "Nos", supplier: "", rate: 0, asset_category: "", expense_account: "" }
const itemForm = reactive({ company: ctx.value.default_company || "", ...emptyItem })
const accountOrigin = ref(false)
const disableItem = ref(null)
const disableReason = ref("")
const disabling = ref(false)
const openingForm = reactive({ company: ctx.value.default_company || "", posting_date: new Date().toISOString().slice(0, 10), items: [{ item_code: "", warehouse: "", qty: 0, valuation_rate: 0 }] })

const requestOrigin = () => accountOrigin.value ? "Accounts" : undefined

function openCreateItem() { accountOrigin.value = false; creating.value = true }

function openDisable(item) { disableItem.value = item; disableReason.value = "" }

async function submitDisable() {
	disabling.value = true
	try {
		const result = await call("create_catalog_disable_request", {
			item_code: disableItem.value.name, reason: disableReason.value, company: ctx.value.default_company,
		})
		toast(`Disable request ${result.name} is ${result.status}`)
		disableItem.value = null
		await load()
	} catch (error) { toastError(error) }
	finally { disabling.value = false }
}

async function load(append = false) {
	const loadId = ++latestLoad
	loading.value = true
	try {
		const result = await call("get_catalog", {
			search: search.value, item_type: typeFilter.value, item_group: groupFilter.value,
			source: sourceFilter.value, stock_status: stockFilter.value,
			sort_by: sortBy.value, sort_order: sortOrder.value,
			start: append ? rows.value.length : 0, page_length: 50,
		})
		if (loadId !== latestLoad) return
		rows.value = append ? [...rows.value, ...result.rows] : result.rows
		total.value = result.total_count
	} catch (error) {
		if (loadId === latestLoad) toastError(error)
	} finally {
		if (loadId === latestLoad) loading.value = false
	}
}

async function loadFilterOptions() {
	try { filterOptions.value = await call("get_catalog_filter_options") } catch (error) { toastError(error) }
}

function clearFilters() {
	search.value = ""
	typeFilter.value = ""
	groupFilter.value = ""
	sourceFilter.value = ""
	stockFilter.value = ""
	sortBy.value = "item_name"
	sortOrder.value = "asc"
}

const allDisplayedSelected = computed(() => rows.value.length > 0 && rows.value.every((item) => selectedItemCodes.value.has(item.name)))

function clearSelection() { selectedItemCodes.value = new Set() }

function toggleItemSelection(itemCode) {
	const selected = new Set(selectedItemCodes.value)
	if (selected.has(itemCode)) selected.delete(itemCode)
	else selected.add(itemCode)
	selectedItemCodes.value = selected
}

function toggleDisplayedSelection() {
	const selected = new Set(selectedItemCodes.value)
	if (allDisplayedSelected.value) rows.value.forEach((item) => selected.delete(item.name))
	else rows.value.forEach((item) => selected.add(item.name))
	selectedItemCodes.value = selected
}

function openSupplierLinking() {
	accountOrigin.value = false
	supplierLinkForm.company = ctx.value.default_company || ""
	supplierLinkForm.supplier = ""
	supplierLinking.value = true
}

async function createSupplierLinkRequest() {
	supplierLinkSaving.value = true
	try {
		const result = await call("create_catalog_supplier_link_request", {
			data: {
				company: supplierLinkForm.company,
				request_origin: requestOrigin(),
				supplier: supplierLinkForm.supplier,
				item_codes: [...selectedItemCodes.value],
			},
		})
		if (result.name) toast(`Catalog request ${result.name} is ${result.status} for ${result.requested} item(s).`)
		else toast(`All ${result.already_linked} selected item(s) are already linked to this supplier.`)
		clearSelection()
		supplierLinking.value = false
		load()
	} catch (error) {
		toastError(error)
	} finally {
		supplierLinkSaving.value = false
	}
}

function openGroupChanging() {
	accountOrigin.value = false
	groupChangeForm.company = ctx.value.default_company || ""
	groupChangeForm.item_group = ""
	groupChanging.value = true
}

async function createItemGroupChangeRequest() {
	groupChangeSaving.value = true
	try {
		const result = await call("create_catalog_item_group_change_request", {
			data: {
				company: groupChangeForm.company,
				request_origin: requestOrigin(),
				item_group: groupChangeForm.item_group,
				item_codes: [...selectedItemCodes.value],
			},
		})
		if (result.name) toast(`Catalog request ${result.name} is ${result.status} for ${result.requested} item(s).`)
		else toast(`All ${result.already_correct} selected item(s) already use this Item Group.`)
		clearSelection()
		groupChanging.value = false
		load()
	} catch (error) {
		toastError(error)
	} finally {
		groupChangeSaving.value = false
	}
}

async function createItem() {
	saving.value = true
	try {
		const result = await call("create_controlled_item", { data: { ...itemForm, request_origin: requestOrigin() } })
		toast(`Catalog request ${result.name} is ${result.status}`)
		Object.assign(itemForm, emptyItem)
		creating.value = false
		load()
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

async function openItemEdit(item) {
	try {
		accountOrigin.value = false
		const result = await call("get_catalog_item_edit_form", { item_code: item.name })
		Object.assign(itemEditForm, { company: ctx.value.default_company || "", item_code: item.name, ...result })
		editingItem.value = true
	} catch (error) {
		toastError(error)
	}
}

async function createItemEditRequest() {
	itemEditSaving.value = true
	try {
		const result = await call("create_catalog_item_edit_request", { data: { ...itemEditForm, request_origin: requestOrigin() } })
		toast(`Catalog edit request ${result.name} is ${result.status}`)
		editingItem.value = false
		load()
	} catch (error) {
		toastError(error)
	} finally {
		itemEditSaving.value = false
	}
}

async function onWorkbookChosen(event) {
	accountOrigin.value = false
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
		const result = await call("import_catalog_workbook", { file_url, request_origin: requestOrigin() })
		toast(`Catalog request ${result.name} is ${result.status}`)
		importState.value = null
	} catch (error) {
		importState.value = { ...importState.value, stage: "preview" }
		toastError(error)
	}
}

async function downloadTemplate() {
	try { window.location.assign((await call("download_catalog_template")).file_url) } catch (error) { toastError(error) }
}

async function exportCatalog(fileFormat) {
	exporting.value = fileFormat
	try {
		const result = await call("download_catalog_export", {
			file_format: fileFormat,
			search: search.value,
			item_type: typeFilter.value,
			item_group: groupFilter.value,
			source: sourceFilter.value,
			stock_status: stockFilter.value,
			sort_by: sortBy.value,
			sort_order: sortOrder.value,
		})
		window.location.assign(result.file_url)
		toast(`${result.rows} catalog item(s) exported`)
	} catch (error) {
		toastError(error)
	} finally {
		exporting.value = ""
	}
}

async function showStock(item) {
	stockItem.value = item
	try { stockRows.value = (await call("get_catalog_stock", { item_code: item.name })).rows } catch (error) { toastError(error) }
}

async function openPriceRequest(item) {
	priceItem.value = item
	Object.assign(priceForm, { company: ctx.value.default_company, item_code: item.name,
		supplier: "", price_list: "Standard Buying", proposed_rate: "", reason: "" })
	await refreshPriceContext()
}

async function refreshPriceContext() {
	if (!priceItem.value) return
	try {
		priceContext.value = await call("get_price_context", {
			item_code: priceForm.item_code, company: priceForm.company,
			supplier: priceForm.supplier, price_list: priceForm.price_list,
		})
	} catch (error) { priceContext.value = null; toastError(error) }
}

async function submitPriceRequest() {
	priceSaving.value = true
	try {
		const result = await call("request_price_change", { data: priceForm })
		toast(`Price request ${result.name}: ${result.status}. Raven delivery status is shown in Price requests.`)
		priceItem.value = null
	} catch (error) { toastError(error) } finally { priceSaving.value = false }
}

function addOpeningRow() { openingForm.items.push({ item_code: "", warehouse: "", qty: 0, valuation_rate: 0 }) }

async function saveOpeningStock() {
	openingSaving.value = true
	try { const result = await call("record_opening_stock", { data: openingForm }); toast(`Opening stock recorded in ${result.name}`); opening.value = false; load() } catch (error) { toastError(error) } finally { openingSaving.value = false }
}

async function runMrgOpeningStock() {
	mrgSnapshotSaving.value = true
	try {
		const result = await call("run_mrg_opening_stock_snapshot", { company: ctx.value.default_company })
		if (result.status === "completed") {
			toast(`MRG opening stock complete: ${result.submitted_documents} reconciliation document(s) submitted.`)
		} else {
			toast(`MRG opening stock is waiting on ${result.preflight_error_count} preflight issue(s). Review request ${result.catalog_requests.join(", ") || "status"}.`)
		}
		load()
	} catch (error) {
		toastError(error)
	} finally {
		mrgSnapshotSaving.value = false
	}
}

watch(search, debounce(() => { clearSelection(); load() }, 300))
watch([typeFilter, groupFilter, sourceFilter, stockFilter, sortBy, sortOrder], () => { clearSelection(); load() })
onMounted(() => { load(); loadFilterOptions() })
</script>

<template>
	<PageHeader title="Controlled Catalog" subtitle="Approved items that can be ordered, received and transferred." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Controlled Catalog' }]">
		<template v-if="ctx.can_manage_catalog" #actions>
			<button class="cp-btn" :disabled="!!exporting" @click="exportCatalog('csv')">{{ exporting === "csv" ? "Exporting…" : "Export CSV" }}</button>
			<button class="cp-btn" :disabled="!!exporting" @click="exportCatalog('xlsx')">{{ exporting === "xlsx" ? "Exporting…" : "Export Excel" }}</button>
			<button class="cp-btn" @click="downloadTemplate">Download template</button>
			<button class="cp-btn" @click="fileInput.click()">Import workbook</button>
			<button v-if="ctx.can_opening_stock" class="cp-btn" @click="opening = true">Opening stock</button>
			<button v-if="ctx.can_opening_stock && ctx.default_company === 'M R G INSULATION WORKS L.L.C'" class="cp-btn" :disabled="mrgSnapshotSaving" @click="runMrgOpeningStock">{{ mrgSnapshotSaving ? "Uploading MRG stock…" : "Upload MRG stock report" }}</button>
			<button class="cp-btn" :disabled="!selectedItemCodes.size" @click="openSupplierLinking">Add supplier to selected ({{ selectedItemCodes.size }})</button>
			<button class="cp-btn" :disabled="!selectedItemCodes.size" @click="openGroupChanging">Change group for selected ({{ selectedItemCodes.size }})</button>
			<button class="cp-btn primary" @click="openCreateItem">New catalog request</button>
			<input ref="fileInput" type="file" accept=".xlsx" hidden @change="onWorkbookChosen" />
		</template>
	</PageHeader>
	<CatalogTabs />

	<div class="cp-filters">
		<input v-model="search" class="cp-input cp-search" placeholder="Search description or item code" autofocus />
		<div class="cp-segmented">
			<button :class="{ active: !typeFilter }" :aria-pressed="!typeFilter" @click="typeFilter = ''">All</button>
			<button v-for="type in ['Stockable', 'Consumable', 'Asset', 'Service']" :key="type" :class="{ active: typeFilter === type }" :aria-pressed="typeFilter === type" @click="typeFilter = type">{{ type }}</button>
		</div>
	</div>
	<div class="cp-filters cp-catalog-controls">
		<label class="cp-field"><span>Item group</span><select v-model="groupFilter" class="cp-input"><option value="">All groups</option><option v-for="group in filterOptions.item_groups" :key="group" :value="group">{{ group }}</option></select></label>
		<label class="cp-field"><span>Source</span><select v-model="sourceFilter" class="cp-input"><option value="">All sources</option><option v-for="source in filterOptions.sources" :key="source" :value="source">{{ source }}</option></select></label>
		<label class="cp-field"><span>Stock</span><select v-model="stockFilter" class="cp-input"><option value="">Any stock</option><option value="in_stock">In stock</option><option value="out_of_stock">Out of stock</option></select></label>
		<label class="cp-field"><span>Sort by</span><select v-model="sortBy" class="cp-input"><option value="item_name">Description</option><option value="name">Item code</option><option value="item_group">Group</option><option value="controlled_item_type">Type</option><option value="actual_qty">Available stock</option><option value="controlled_catalog_source">Source</option></select></label>
		<label class="cp-field"><span>Direction</span><select v-model="sortOrder" class="cp-input"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
		<button type="button" class="cp-btn cp-clear-filters" @click="clearFilters">Clear filters</button>
	</div>

	<section class="cp-card">
		<table class="cp-table">
			<thead><tr><th v-if="ctx.can_manage_catalog"><input type="checkbox" :checked="allDisplayedSelected" aria-label="Select displayed catalog items" @change="toggleDisplayedSelection" /></th><th>Description</th><th>Group</th><th>Type</th><th class="num">Available stock</th><th>Source</th><th>UOM</th><th /></tr></thead>
			<tbody>
				<tr v-for="item in rows" :key="item.name">
					<td v-if="ctx.can_manage_catalog"><input type="checkbox" :checked="selectedItemCodes.has(item.name)" :aria-label="`Select ${item.item_name}`" @change="toggleItemSelection(item.name)" /></td>
					<td><strong>{{ item.item_name }}</strong><small>{{ item.name }}</small></td>
					<td>{{ item.item_group }}</td>
					<td><span class="cp-pill info">{{ item.controlled_item_type }}</span></td>
					<td class="num"><button v-if="['Stockable', 'Consumable'].includes(item.controlled_item_type)" class="cp-link" @click="showStock(item)">{{ item.actual_qty }}</button><span v-else>—</span></td>
					<td><span class="cp-muted">{{ item.controlled_catalog_source || "—" }}</span></td>
					<td>{{ item.stock_uom }}</td>
					<td><button v-if="ctx.can_manage_catalog" class="cp-btn sm" @click="openItemEdit(item)">Edit request</button><button v-if="ctx.can_request_price_change" class="cp-btn sm" @click="openPriceRequest(item)">Request price change</button><button v-if="ctx.can_disable_catalog" class="cp-btn sm" @click="openDisable(item)">Disable</button></td>
				</tr>
				<tr v-if="!loading && !rows.length"><td :colspan="ctx.can_manage_catalog ? 8 : 7" class="cp-empty-row">No approved items match these filters.</td></tr>
			</tbody>
		</table>
		<footer v-if="rows.length" class="cp-card-foot">
			<span>{{ rows.length }} of {{ total }} items</span>
			<button v-if="rows.length < total" class="cp-btn sm" :disabled="loading" @click="load(true)">Load more</button>
		</footer>
	</section>

	<Modal v-if="supplierLinking" :title="`Add supplier to ${selectedItemCodes.size} selected item(s)`" @close="supplierLinking = false">
		<form id="cp-supplier-link-form" class="cp-stack" @submit.prevent="createSupplierLinkRequest">
			<CatalogOriginChoice v-model="accountOrigin" :can-choose="ctx.can_create_catalog_as_accounts && ctx.can_purchase" />
			<p class="cp-muted">This creates one catalog request. It adds the selected supplier only after the normal approval workflow; buying prices are not changed.</p>
			<LinkSelect v-model="supplierLinkForm.supplier" doctype="Supplier" label="Supplier" :required="true" :filters="{ disabled: 0 }" />
		</form>
		<template #footer><button class="cp-btn" @click="supplierLinking = false">Cancel</button><button class="cp-btn primary" form="cp-supplier-link-form" type="submit" :disabled="supplierLinkSaving">{{ supplierLinkSaving ? "Submitting…" : "Submit catalog request" }}</button></template>
	</Modal>

	<Modal v-if="groupChanging" :title="`Change group for ${selectedItemCodes.size} selected item(s)`" @close="groupChanging = false">
		<form id="cp-group-change-form" class="cp-stack" @submit.prevent="createItemGroupChangeRequest">
			<CatalogOriginChoice v-model="accountOrigin" :can-choose="ctx.can_create_catalog_as_accounts && ctx.can_purchase" />
			<p class="cp-muted">This creates one catalog request. The Item Group changes only after normal approval; item codes, stock, UOMs, suppliers, and prices are not changed.</p>
			<LinkSelect v-model="groupChangeForm.item_group" doctype="Item Group" label="Item group" :required="true" :filters="{ is_group: 0 }" />
		</form>
		<template #footer><button class="cp-btn" @click="groupChanging = false">Cancel</button><button class="cp-btn primary" form="cp-group-change-form" type="submit" :disabled="groupChangeSaving">{{ groupChangeSaving ? "Submitting…" : "Submit catalog request" }}</button></template>
	</Modal>

	<Modal v-if="disableItem" :title="`Disable catalog item · ${disableItem.item_name}`" @close="disableItem = null">
		<form id="cp-disable-item-form" class="cp-stack" @submit.prevent="submitDisable">
			<p class="cp-muted">{{ ctx.can_approve_catalog_ceo ? "This will disable the item immediately." : "The item remains available until CEO approval." }} Historical orders, stock, and accounts records are preserved.</p>
			<label class="cp-field"><span>Reason<i>*</i></span><textarea v-model="disableReason" class="cp-input" rows="3" required /></label>
		</form>
		<template #footer><button class="cp-btn" @click="disableItem = null">Cancel</button><button class="cp-btn primary" form="cp-disable-item-form" type="submit" :disabled="disabling">{{ disabling ? "Submitting…" : ctx.can_approve_catalog_ceo ? "Disable item" : "Submit disable request" }}</button></template>
	</Modal>

	<Modal v-if="priceItem" :title="`Request buying price · ${priceItem.item_name}`" @close="priceItem = null">
		<form id="cp-price-request-form" class="cp-stack" @submit.prevent="submitPriceRequest">
			<p class="cp-muted">The current price stays active until a CEO approves this request. Existing orders keep their saved rates.</p>
			<label class="cp-field"><span>Supplier scope</span><select v-model="priceForm.supplier" class="cp-input" @change="refreshPriceContext"><option value="">General buying price</option><option v-for="supplier in priceContext?.suppliers || []" :key="supplier" :value="supplier">{{ supplier }}</option></select></label>
			<LinkSelect v-model="priceForm.price_list" doctype="Price List" label="Buying price list" :filters="{ buying: 1, enabled: 1 }" @update:modelValue="refreshPriceContext" />
			<p>Current {{ priceForm.supplier || "general" }} price: <strong>{{ priceContext?.rate == null ? "Not set" : `${priceContext.currency} ${priceContext.rate}` }}</strong><br /><small>Item Price: {{ priceContext?.item_price || "New price" }}</small><br /><small v-if="priceContext?.fallback_rate != null">General buying fallback: {{ priceContext.currency }} {{ priceContext.fallback_rate }} ({{ priceContext.fallback_item_price }})</small></p>
			<label class="cp-field"><span>Proposed rate<i>*</i></span><input v-model.number="priceForm.proposed_rate" type="number" min="0.001" step="any" class="cp-input" required /></label>
			<label class="cp-field"><span>Reason<i>*</i></span><textarea v-model="priceForm.reason" class="cp-input" rows="3" required /></label>
			<p><strong>Proposed change:</strong> {{ priceContext?.rate == null ? "New supplier-specific price" : `${priceContext.currency} ${priceContext.rate}` }} → <strong>{{ priceContext?.currency }} {{ priceForm.proposed_rate || "—" }}</strong><span v-if="priceForm.supplier && priceContext?.rate == null && priceContext?.fallback_rate != null"> · The general {{ priceContext.currency }} {{ priceContext.fallback_rate }} rate remains unchanged.</span></p>
			<PriceHistory :item-code="priceForm.item_code" :supplier="priceForm.supplier" :price-list="priceForm.price_list" :company="priceForm.company" />
		</form>
		<template #footer><button class="cp-btn primary" form="cp-price-request-form" type="submit" :disabled="priceSaving">{{ priceSaving ? "Sending…" : "Send for CEO approval" }}</button></template>
	</Modal>

	<Modal v-if="creating" title="New catalog request" wide @close="creating = false">
		<form id="cp-item-form" class="cp-stack" @submit.prevent="createItem">
			<CatalogOriginChoice v-model="accountOrigin" :can-choose="ctx.can_create_catalog_as_accounts && ctx.can_purchase" />
			<div class="cp-grid-2">
				<LinkSelect v-model="itemForm.company" doctype="Company" label="Company" :required="true" />
				<label class="cp-field">
					<span>Item type<i>*</i></span>
					<select v-model="itemForm.item_type" class="cp-input"><option>Stockable</option><option>Consumable</option><option>Asset</option><option>Service</option></select>
				</label>
				<label class="cp-field"><span>Description<i>*</i></span><input v-model="itemForm.item_name" class="cp-input" required /></label>
				<label class="cp-field"><span>Item code</span><input v-model="itemForm.item_code" class="cp-input" placeholder="Auto-generated if empty" /></label>
				<LinkSelect v-model="itemForm.item_group" doctype="Item Group" label="Item group" :required="true" :filters="{ is_group: 0 }" />
				<LinkSelect v-model="itemForm.stock_uom" doctype="UOM" label="Stock UOM" :required="true" />
				<LinkSelect v-model="itemForm.supplier" doctype="Supplier" label="Supplier" :required="true" />
				<label class="cp-field"><span>Buying rate</span><input v-model.number="itemForm.rate" type="number" min="0" step="any" class="cp-input" /><small class="cp-hint">A positive rate is approved by Accounts, then the CEO, before it becomes active.</small></label>
				<LinkSelect v-if="itemForm.item_type === 'Asset'" v-model="itemForm.asset_category" doctype="Asset Category" label="Asset category" placeholder="Company default" />
				<LinkSelect v-if="itemForm.item_type === 'Service'" v-model="itemForm.expense_account" doctype="Account" label="Service expense account" placeholder="Company default" :filters="{ company: itemForm.company, is_group: 0 }" />
			</div>
			<p class="cp-hint">Choose the unit used for stock, orders, receipts and buying prices.</p>
		</form>
		<template #footer>
			<button class="cp-btn" @click="creating = false">Cancel</button>
			<button type="submit" form="cp-item-form" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : "Submit request" }}</button>
		</template>
	</Modal>

	<Modal v-if="editingItem" :title="`Edit catalog item · ${itemEditForm.item_code}`" wide @close="editingItem = false">
		<form id="cp-item-edit-form" class="cp-stack" @submit.prevent="createItemEditRequest">
			<CatalogOriginChoice v-model="accountOrigin" :can-choose="ctx.can_create_catalog_as_accounts && ctx.can_purchase" />
			<p class="cp-hint">Item Code is permanent. All changes below take effect only after Accounts and CEO approval.</p>
			<div class="cp-grid-2">
				<label class="cp-field"><span>Item code</span><input :value="itemEditForm.item_code" class="cp-input" disabled /></label>
				<label class="cp-field"><span>Item type<i>*</i></span><select v-model="itemEditForm.item_type" class="cp-input"><option>Stockable</option><option>Consumable</option><option>Asset</option><option>Service</option></select></label>
				<label class="cp-field"><span>Description<i>*</i></span><input v-model="itemEditForm.item_name" class="cp-input" required /></label>
				<LinkSelect v-model="itemEditForm.item_group" doctype="Item Group" label="Item group" :required="true" :filters="{ is_group: 0 }" />
				<LinkSelect v-model="itemEditForm.stock_uom" doctype="UOM" label="Stock UOM" :required="true" />
				<LinkSelect v-model="itemEditForm.supplier" doctype="Supplier" label="Supplier" :required="true" />
				<label class="cp-field"><span>Buying rate</span><input v-model.number="itemEditForm.rate" type="number" min="0" step="any" class="cp-input" /></label>
				<LinkSelect v-if="itemEditForm.item_type === 'Asset'" v-model="itemEditForm.asset_category" doctype="Asset Category" label="Asset category" />
				<LinkSelect v-if="itemEditForm.item_type === 'Service'" v-model="itemEditForm.expense_account" doctype="Account" label="Service expense account" :filters="{ company: itemEditForm.company, is_group: 0 }" />
			</div>
		</form>
		<template #footer><button class="cp-btn" @click="editingItem = false">Cancel</button><button type="submit" form="cp-item-edit-form" class="cp-btn primary" :disabled="itemEditSaving">{{ itemEditSaving ? 'Submitting…' : 'Submit for approval' }}</button></template>
	</Modal>

	<Modal v-if="importState" title="Import catalog workbook" @close="importState.stage === 'preview' && (importState = null)">
		<CatalogOriginChoice v-if="importState.stage === 'preview'" v-model="accountOrigin" :can-choose="ctx.can_create_catalog_as_accounts && ctx.can_purchase" />
		<p class="cp-hint">Each row must include an existing Supplier. Use its Supplier ID from the selector, together with Description, Item Group, and the type-specific columns.</p>
		<p v-if="importState.stage === 'uploading'" class="cp-muted">Uploading and checking {{ importState.file }}…</p>
		<p v-else-if="importState.stage === 'importing'" class="cp-muted">Importing {{ importState.file }}…</p>
		<template v-else>
			<p><strong>{{ importState.file }}</strong></p>
			<div class="cp-stats compact">
				<div class="cp-stat static"><small>Valid rows</small><strong>{{ importState.preview.valid_rows }}</strong></div>
				<div class="cp-stat static"><small>New items</small><strong>{{ importState.preview.create }}</strong></div>
				<div class="cp-stat static"><small>Existing reused</small><strong>{{ importState.preview.reuse }}</strong></div>
			</div>
			<div v-if="importState.preview.errors.length" class="cp-exceptions">
				<strong>{{ importState.preview.errors.length }} errors must be corrected</strong>
				<ul>
					<li v-for="row in importState.preview.errors.slice(0, 20)" :key="`${row.row}-${row.reason}`">Row {{ row.row }}<template v-if="row.item"> · {{ row.item }}</template>: {{ row.reason }}</li>
				</ul>
			</div>
		</template>
		<template v-if="importState.stage === 'preview'" #footer>
			<button class="cp-btn" @click="importState = null">Cancel</button>
			<button class="cp-btn primary" :disabled="importState.preview.errors.length" @click="confirmImport">Submit for approval</button>
		</template>
	</Modal>

	<Modal v-if="stockItem" :title="`Warehouse stock · ${stockItem.item_name}`" @close="stockItem = null">
		<table class="cp-table"><thead><tr><th>Warehouse</th><th class="num">Qty</th><th class="num">Valuation rate</th></tr></thead><tbody><tr v-for="row in stockRows" :key="row.warehouse"><td>{{ row.warehouse }}</td><td class="num">{{ row.actual_qty }}</td><td class="num">{{ row.valuation_rate }}</td></tr><tr v-if="!stockRows.length"><td colspan="3" class="cp-empty-row">No warehouse stock.</td></tr></tbody></table>
	</Modal>

	<Modal v-if="opening" title="Opening stock balance" wide @close="opening = false">
		<form id="cp-opening-form" class="cp-stack" @submit.prevent="saveOpeningStock"><div class="cp-grid-2"><LinkSelect v-model="openingForm.company" doctype="Company" label="Company" :required="true" /><label class="cp-field"><span>Posting date<i>*</i></span><input v-model="openingForm.posting_date" type="date" class="cp-input" required /></label></div><table class="cp-table cp-edit-table"><thead><tr><th>Catalog item</th><th>Warehouse</th><th class="num">Qty</th><th class="num">Valuation rate</th><th /></tr></thead><tbody><tr v-for="(row, index) in openingForm.items" :key="index"><td><LinkSelect v-model="row.item_code" doctype="Item" label="" :filters="{ controlled_procurement_catalog: 1, is_stock_item: 1 }" /></td><td><LinkSelect v-model="row.warehouse" doctype="Warehouse" label="" :filters="{ company: openingForm.company, is_group: 0 }" /></td><td><input v-model.number="row.qty" class="cp-input num" type="number" min="0" /></td><td><input v-model.number="row.valuation_rate" class="cp-input num" type="number" min="0" /></td><td><button type="button" class="cp-remove" :disabled="openingForm.items.length === 1" @click="openingForm.items.splice(index, 1)">×</button></td></tr></tbody></table><button type="button" class="cp-link" @click="addOpeningRow">+ Add line</button></form>
		<template #footer><button class="cp-btn" @click="opening = false">Cancel</button><button class="cp-btn primary" type="submit" form="cp-opening-form" :disabled="openingSaving">{{ openingSaving ? "Recording…" : "Record opening stock" }}</button></template>
	</Modal>
</template>
