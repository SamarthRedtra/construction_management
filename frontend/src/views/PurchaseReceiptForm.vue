<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { debounce, formatCurrency, formatDate, formatNumber, today, companyFilters, session } from "@/utils"
import AllocationFields from "@/components/AllocationFields.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import TaxSection from "@/components/TaxSection.vue"
import VatSelect from "@/components/VatSelect.vue"
import { useTaxes } from "@/taxes"

const route = useRoute()
const router = useRouter()
const props = defineProps({ name: { type: String, default: "" } })
const editing = computed(() => Boolean(props.name))
const form = reactive({ purchase_order: "", supplier_delivery_note: "", warehouse: "", received_on: today(), project: "", bill_no: "", boq_item: "", taxes_and_charges: null, items: [] })
const openOrders = ref([])
const availableLines = ref([])
const poQuery = ref("")
const poSearching = ref(false)
const poOpen = ref(false)
const loadingLines = ref(false)
const saving = ref(false)
const hydrating = ref(false)

// app-created POs need catalog items and a full BOQ allocation; Desk POs only need a project
const isControlledOrder = computed(() => form.items.length ? Boolean(form.items[0].controlled) : true)
const selectedOrder = computed(() => openOrders.value.find((row) => row.name === form.purchase_order))
const isOpenLpo = computed(() => Boolean(selectedOrder.value?.is_open_po || availableLines.value[0]?.is_open_lpo))
const total = computed(() => form.items.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))
// no company default here: the tax template follows the chosen purchase order
const { templates: taxTemplates, totals, loading: taxLoading, lineTax } = useTaxes("Purchase Receipt", form, { defaultTemplate: false })

async function loadLines() {
	form.items = []
	if (!form.purchase_order) return
	loadingLines.value = true
	try {
		const rows = await call("get_purchase_order_items", { purchase_order: form.purchase_order })
		availableLines.value = rows
		form.items = rows.map((row) => ({ ...row, client_key: window.crypto.randomUUID(), qty: row.remaining_qty, po_warehouse: row.warehouse, warehouse: "", use_override: false }))
		// Desk POs already say where each line goes; start the receive note there
		if (!form.warehouse && rows[0]?.warehouse) form.warehouse = rows[0].warehouse
		// start from the PO's allocation; the receiver can change it below
		const first = rows.find((row) => row.project) || {}
		Object.assign(form, { project: first.project || "", bill_no: first.bill_no || "", boq_item: first.boq_item || "" })
		// VAT follows the order; each line keeps the PO line's choice unless changed here
		form.taxes_and_charges = rows[0]?.po_taxes_and_charges || ""
	} catch (error) {
		toastError(error)
	} finally {
		loadingLines.value = false
	}
}
function addRemainingLines() {
	const present = new Set(form.items.map((row) => row.purchase_order_item))
	for (const row of availableLines.value) {
		if (!present.has(row.purchase_order_item)) form.items.push({ ...row, client_key: window.crypto.randomUUID(), qty: 0, warehouse: "", use_override: false })
	}
}

function splitLine(row) {
	const { name, ...source } = row
	form.items.push({ ...source, client_key: window.crypto.randomUUID(), qty: 0, warehouse: "", use_override: false })
}

function availableForRow(row) {
	const usedElsewhere = form.items
		.filter((other) => other !== row && other.purchase_order_item === row.purchase_order_item)
		.reduce((sum, other) => sum + (Number(other.qty) || 0), 0)
	return Math.max(0, Number(row.remaining_qty || 0) - usedElsewhere)
}

function exceedsPending(row) {
	return !isOpenLpo.value && form.items
		.filter((other) => other.purchase_order_item === row.purchase_order_item)
		.reduce((sum, other) => sum + (Number(other.qty) || 0), 0) > Number(row.remaining_qty || 0) + 0.0001
}

const searchOrders = debounce(async () => {
	poSearching.value = true
	try {
		const result = await call("get_open_lpos", { search: poQuery.value.trim(), page_length: 20 })
		openOrders.value = result.rows
	} catch (error) { toastError(error) }
	finally { poSearching.value = false }
}, 250)

async function chooseOrder(order) {
	form.purchase_order = order.name
	poQuery.value = order.name
	poOpen.value = false
	await loadLines()
}
function closeOrderSearch() { setTimeout(() => { poOpen.value = false; if (!form.purchase_order) poQuery.value = "" }, 180) }

async function save() {
	saving.value = true
	try {
		const items = form.items
			.filter((row) => Number(row.qty) > 0)
			.map((row) => ({
				...row,
				warehouse: row.warehouse || form.warehouse,
				// without an override the line takes the receipt's allocation
				...(row.use_override ? {} : { project: "", bill_no: "", boq_item: "" }),
			}))
		const result = editing.value
			? await call("update_purchase_receipt", { name: props.name, data: { ...form, items } })
			: await call("create_purchase_receipt", { data: { ...form, items } })
		toast(`Receive note ${result.name} ${editing.value ? "updated" : "created as draft"}`)
		router.push(`/receipts/${result.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

// receipts are always booked to the receiving warehouse's project (site rule), so keep the form in step
const warehouseNote = ref("")
async function projectFor(warehouse) {
	return warehouse ? call("get_warehouse_project", { warehouse }) : ""
}

watch(() => form.warehouse, async (warehouse) => {
	if (hydrating.value) return
	warehouseNote.value = ""
	const project = await projectFor(warehouse)
	if (project && project !== form.project) {
		Object.assign(form, { project, bill_no: "", boq_item: "" })
		warehouseNote.value = `Project set to ${project} because ${warehouse} is that project's warehouse. Pick its Bill No and BOQ Item.`
	}
})

async function setLineWarehouse(row, warehouse) {
	row.warehouse = warehouse
	const project = await projectFor(warehouse)
	const current = row.use_override ? row.project : form.project
	if (project && project !== current) {
		Object.assign(row, { use_override: true, project, bill_no: "", boq_item: "" })
		toast(`Line moved to project ${project} (warehouse ${warehouse}). Pick its Bill No and BOQ Item.`)
	}
}

onMounted(async () => {
	if (editing.value) {
		try {
			hydrating.value = true
			const doc = await call("get_controlled_document", { doctype: "Purchase Receipt", name: props.name })
			if (doc.docstatus !== 0) { router.replace(`/receipts/${props.name}`); return }
			const po = doc.items?.[0]?.purchase_order || doc.custom_purchase_order
			form.purchase_order = po
			poQuery.value = po
			const result = await call("get_open_lpos", { search: po, page_length: 20 })
			openOrders.value = result.rows
			const remaining = await call("get_purchase_order_items", { purchase_order: po })
			availableLines.value = remaining
			Object.assign(form, { supplier_delivery_note: doc.supplier_delivery_note || "", warehouse: doc.items?.[0]?.warehouse || "",
				received_on: String(doc.posting_date).slice(0, 10), project: doc.project || "", bill_no: doc.bill_no || "",
				boq_item: doc.boq_item || "", taxes_and_charges: doc.taxes_and_charges || "" })
			form.items = (doc.items || []).map((row) => ({ ...row, client_key: window.crypto.randomUUID(), controlled: doc.controlled_procurement, qty: row.qty, rate: row.rate,
				remaining_qty: remaining.find((pending) => pending.purchase_order_item === row.purchase_order_item)?.remaining_qty ?? row.qty,
				vat: row.vat || "standard", use_override: row.project !== form.project || row.bill_no !== form.bill_no || row.boq_item !== form.boq_item }))
		} catch (error) { toastError(error) }
		finally { hydrating.value = false }
	} else if (route.query.po) {
		const result = await call("get_open_lpos", { search: String(route.query.po), page_length: 20 })
		const order = result.rows.find((row) => row.name === String(route.query.po))
		if (order) { openOrders.value = result.rows; await chooseOrder(order) }
	}
})
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader :title="editing ? `Edit ${name}` : 'New Receive Note'" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Receive Notes', to: '/receipts' }, { label: editing ? name : 'New' }]">
			<template #actions>
				<RouterLink :to="editing ? `/receipts/${name}` : '/receipts'" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving || !form.items.length">{{ saving ? "Saving…" : editing ? "Save changes" : "Save receive note" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Receive note</h2>
			<div class="cp-grid-3">
				<div class="cp-field" style="position: relative">
					<span>Purchase order<i>*</i></span>
					<input v-model="poQuery" class="cp-input" required :readonly="editing" autocomplete="off" placeholder="Type a PO number" @focus="poOpen = true; searchOrders()" @input="form.purchase_order = ''; poOpen = true; searchOrders()" @blur="closeOrderSearch" />
					<div v-if="poOpen && !editing" class="cp-options" style="position: absolute; z-index: 20; width: 100%; max-height: 240px; overflow: auto">
						<button v-for="order in openOrders" :key="order.name" type="button" @mousedown.prevent="chooseOrder(order)"><strong>{{ order.name }}</strong><small>{{ order.supplier_name || order.supplier }} · {{ Math.round(order.per_received) }}% received</small></button>
						<span v-if="!poSearching && !openOrders.length" class="cp-hint">No receivable POs found</span>
					</div>
					<small v-if="selectedOrder" class="cp-hint">{{ [selectedOrder.project, `due ${formatDate(selectedOrder.schedule_date)}`].filter(Boolean).join(" · ") }}</small>
				</div>
				<div>
					<LinkSelect v-model="form.warehouse" doctype="Warehouse" label="Receiving warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
					<small class="cp-hint">Where the goods land on site.</small>
				</div>
				<label class="cp-field"><span>Received on</span><input v-model="form.received_on" type="date" class="cp-input" required /></label>
			</div>
			<div class="cp-grid-3">
				<label class="cp-field"><span>Supplier DO No.<i>*</i></span><input v-model.trim="form.supplier_delivery_note" class="cp-input" required placeholder="Enter supplier delivery note number" /></label>
			</div>
		</section>

		<section v-if="form.purchase_order && !loadingLines" class="cp-section">
			<h2 class="cp-section-title">Allocation</h2>
			<AllocationFields :key="form.purchase_order" :boq-optional="!isControlledOrder || session.context.boq_allocation_mode === 'project_only'" :model-value="{ project: form.project, bill_no: form.bill_no, boq_item: form.boq_item }" @update:model-value="Object.assign(form, $event)" />
			<p v-if="session.context.boq_allocation_mode === 'project_only'" class="cp-hint">For {{ session.context.default_company }}, Project is required; Bill No and BOQ Item are optional.</p>
			<p v-if="warehouseNote" class="cp-hint cp-warn">{{ warehouseNote }}</p>
			<p class="cp-hint">Pre-filled from the purchase order. Change it to book this receive note against a different project / bill / BOQ item. The project must match the receiving warehouse's project.</p>
			<p v-if="!isControlledOrder" class="cp-hint">This PO was raised in Desk: a Project is required, Bill No and BOQ Item are optional.</p>
		</section>

		<section v-if="form.purchase_order" class="cp-section">
			<div class="cp-section-bar"><h2 class="cp-section-title">Items to receive</h2><button v-if="availableLines.some((row) => !form.items.some((item) => item.purchase_order_item === row.purchase_order_item))" type="button" class="cp-link" @click="addRemainingLines">+ Add PO items</button></div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th>Description</th><th>Allocation</th><th class="num">Pending</th><th class="num" style="width: 120px">Receive qty</th><th style="width: 220px">Warehouse override</th><th style="width: 104px">VAT</th><th class="num">Amount</th><th>Actions</th></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="row.client_key">
						<tr>
							<td><strong>{{ row.item_name || row.item_code }}</strong><small>{{ [row.item_code, row.controlled_item_type].filter(Boolean).join(" · ") }}</small></td>
							<td>
								<template v-if="row.use_override">{{ row.project || "—" }}<small>{{ [row.bill_no, row.boq_item].filter(Boolean).join(" · ") }}</small></template>
								<span v-else class="cp-muted">As receive note</span>
								<button type="button" class="cp-link sm cp-line-action" @click="row.use_override = !row.use_override">{{ row.use_override ? "Use receive note allocation" : "Change for this line" }}</button>
							</td>
							<td class="num">{{ formatNumber(row.remaining_qty) }} <span class="cp-muted">{{ row.uom }}</span></td>
							<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0" step="any" :max="isOpenLpo ? undefined : availableForRow(row)" /><small v-if="exceedsPending(row)" class="cp-overdue">Combined qty exceeds pending</small></td>
							<td><LinkSelect :model-value="row.warehouse" doctype="Warehouse" @update:model-value="setLineWarehouse(row, $event)" :placeholder="form.warehouse || 'Same as receive note'" :filters="companyFilters({ is_group: 0 })" /></td>
							<td><VatSelect v-model="row.vat" /><small class="cp-line-vat">{{ formatCurrency(lineTax(index)) }}</small></td>
							<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0)) }}</td>
							<td><button type="button" class="cp-link sm" @click="splitLine(row)">Split</button><button type="button" class="cp-remove" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
						</tr>
						<tr v-if="row.use_override" class="cp-subrow">
							<td colspan="8"><AllocationFields :model-value="row" :boq-optional="!isControlledOrder || session.context.boq_allocation_mode === 'project_only'" @update:model-value="Object.assign(row, $event)" /></td>
						</tr>
						</template>
						<tr v-if="loadingLines"><td colspan="8" class="cp-empty-row">Loading remaining quantities…</td></tr>
						<tr v-else-if="!form.items.length"><td colspan="8" class="cp-empty-row">This purchase order has nothing left to receive.</td></tr>
					</tbody>
					<tfoot v-if="form.items.length"><tr><td colspan="6" class="num">Net total</td><td class="num"><strong>{{ formatCurrency(total) }}</strong></td><td /></tr></tfoot>
				</table>
			</div>
			<p class="cp-hint">Set a line's receive qty to 0 to skip it.<template v-if="isOpenLpo"> Open LPO quantities may exceed the pending amount.</template></p>
			<TaxSection v-if="form.items.length" v-model="form.taxes_and_charges" :templates="taxTemplates" :totals="totals" :loading="taxLoading" :subtotal="total" />
		</section>
	</form>
</template>
