<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { formatCurrency, formatDate, formatNumber, today, companyFilters } from "@/utils"
import AllocationFields from "@/components/AllocationFields.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import TaxSection from "@/components/TaxSection.vue"
import VatSelect from "@/components/VatSelect.vue"
import { useTaxes } from "@/taxes"

const route = useRoute()
const router = useRouter()
const form = reactive({ purchase_order: "", warehouse: "", received_on: today(), project: "", bill_no: "", boq_item: "", taxes_and_charges: null, items: [] })
const openOrders = ref([])
const loadingLines = ref(false)
const saving = ref(false)

const selectedOrder = computed(() => openOrders.value.find((row) => row.name === form.purchase_order))
const total = computed(() => form.items.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))
// no company default here: the tax template follows the chosen purchase order
const { templates: taxTemplates, totals, loading: taxLoading, lineTax } = useTaxes("Purchase Receipt", form, { defaultTemplate: false })

async function loadLines() {
	form.items = []
	if (!form.purchase_order) return
	loadingLines.value = true
	try {
		const rows = await call("get_purchase_order_items", { purchase_order: form.purchase_order })
		form.items = rows.map((row) => ({ ...row, qty: row.remaining_qty, warehouse: "", use_override: false }))
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
		const result = await call("create_purchase_receipt", { data: { ...form, items } })
		toast(`Purchase receipt ${result.name} created as draft`)
		router.push(`/receipts/${result.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

watch(() => form.purchase_order, loadLines)

// receipts are always booked to the receiving warehouse's project (site rule), so keep the form in step
const warehouseNote = ref("")
async function projectFor(warehouse) {
	return warehouse ? call("get_warehouse_project", { warehouse }) : ""
}

watch(() => form.warehouse, async (warehouse) => {
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
	const result = await call("get_open_lpos", { page_length: 200, controlled_only: 1 })
	openOrders.value = result.rows
	if (route.query.po) form.purchase_order = String(route.query.po)
})
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader title="New Purchase Receipt" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Purchase Receipts', to: '/receipts' }, { label: 'New' }]">
			<template #actions>
				<RouterLink to="/receipts" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving || !form.items.length">{{ saving ? "Saving…" : "Confirm receipt" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Receipt</h2>
			<div class="cp-grid-3">
				<label class="cp-field">
					<span>Purchase order<i>*</i></span>
					<select v-model="form.purchase_order" class="cp-input" required>
						<option value="">— Select open PO —</option>
						<option v-for="order in openOrders" :key="order.name" :value="order.name">
							{{ order.name }} · {{ order.supplier_name || order.supplier }} · {{ Math.round(order.per_received) }}% received
						</option>
					</select>
					<small v-if="selectedOrder" class="cp-hint">{{ [selectedOrder.project, `due ${formatDate(selectedOrder.schedule_date)}`].filter(Boolean).join(" · ") }}</small>
				</label>
				<div>
					<LinkSelect v-model="form.warehouse" doctype="Warehouse" label="Receiving warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
					<small class="cp-hint">Where the goods land on site.</small>
				</div>
				<label class="cp-field"><span>Received on</span><input v-model="form.received_on" type="date" class="cp-input" required /></label>
			</div>
		</section>

		<section v-if="form.purchase_order && !loadingLines" class="cp-section">
			<h2 class="cp-section-title">Allocation</h2>
			<AllocationFields :key="form.purchase_order" :model-value="{ project: form.project, bill_no: form.bill_no, boq_item: form.boq_item }" @update:model-value="Object.assign(form, $event)" />
			<p v-if="warehouseNote" class="cp-hint cp-warn">{{ warehouseNote }}</p>
			<p class="cp-hint">Pre-filled from the purchase order. Change it to book this receipt against a different project / bill / BOQ item. The project must match the receiving warehouse's project.</p>
		</section>

		<section v-if="form.purchase_order" class="cp-section">
			<h2 class="cp-section-title">Items to receive</h2>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th>Description</th><th>Allocation</th><th class="num">Pending</th><th class="num" style="width: 120px">Receive qty</th><th style="width: 220px">Warehouse override</th><th style="width: 104px">VAT</th><th class="num">Amount</th></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="row.purchase_order_item">
						<tr>
							<td><strong>{{ row.item_name || row.item_code }}</strong><small>{{ [row.item_code, row.controlled_item_type].filter(Boolean).join(" · ") }}</small></td>
							<td>
								<template v-if="row.use_override">{{ row.project || "—" }}<small>{{ [row.bill_no, row.boq_item].filter(Boolean).join(" · ") }}</small></template>
								<span v-else class="cp-muted">As receipt</span>
								<button type="button" class="cp-link sm cp-line-action" @click="row.use_override = !row.use_override">{{ row.use_override ? "Use receipt allocation" : "Change for this line" }}</button>
							</td>
							<td class="num">{{ formatNumber(row.remaining_qty) }}</td>
							<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0" step="any" :max="row.remaining_qty" /></td>
							<td><LinkSelect :model-value="row.warehouse" doctype="Warehouse" @update:model-value="setLineWarehouse(row, $event)" :placeholder="form.warehouse || 'Same as receipt'" :filters="companyFilters({ is_group: 0 })" /></td>
							<td><VatSelect v-model="row.vat" /><small class="cp-line-vat">{{ formatCurrency(lineTax(index)) }}</small></td>
							<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0)) }}</td>
						</tr>
						<tr v-if="row.use_override" class="cp-subrow">
							<td colspan="7"><AllocationFields :model-value="row" @update:model-value="Object.assign(row, $event)" /></td>
						</tr>
						</template>
						<tr v-if="loadingLines"><td colspan="7" class="cp-empty-row">Loading remaining quantities…</td></tr>
						<tr v-else-if="!form.items.length"><td colspan="7" class="cp-empty-row">This purchase order has nothing left to receive.</td></tr>
					</tbody>
					<tfoot v-if="form.items.length"><tr><td colspan="6" class="num">Net total</td><td class="num"><strong>{{ formatCurrency(total) }}</strong></td></tr></tfoot>
				</table>
			</div>
			<p class="cp-hint">Set a line's receive qty to 0 to skip it.</p>
			<TaxSection v-if="form.items.length" v-model="form.taxes_and_charges" :templates="taxTemplates" :totals="totals" :loading="taxLoading" :subtotal="total" />
		</section>
	</form>
</template>
