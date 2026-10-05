<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { formatCurrency, formatDate, formatNumber, today } from "@/utils"
import { useTaxes } from "@/taxes"
import PageHeader from "@/components/PageHeader.vue"
import TaxSection from "@/components/TaxSection.vue"
import VatSelect from "@/components/VatSelect.vue"

const route = useRoute()
const router = useRouter()
const form = reactive({
	source: "", // "Purchase Order::PO-0001"
	supplier: "",
	supplier_name: "",
	supplier_invoice_no: "",
	supplier_invoice_date: today(),
	posting_date: today(),
	due_date: "",
	remarks: "",
	taxes_and_charges: null,
	items: [],
})
const sources = ref([])
const availableLines = ref([])
const loadingLines = ref(false)
const saving = ref(false)

const sourceDoctype = computed(() => form.source.split("::")[0] || "")
const sourceName = computed(() => form.source.split("::")[1] || "")
const selectedSource = computed(() => sources.value.find((row) => `${row.doctype}::${row.name}` === form.source))
const total = computed(() => form.items.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))
const { templates: taxTemplates, totals, loading: taxLoading, lineTax } = useTaxes("Purchase Invoice", form, { defaultTemplate: false })

async function loadSources() {
	try {
		sources.value = await call("get_invoice_sources")
	} catch (error) {
		toastError(error)
	}
}

async function loadLines() {
	form.items = []
	availableLines.value = []
	if (!form.source) return
	loadingLines.value = true
	try {
		const result = await call("get_invoice_lines", { source_doctype: sourceDoctype.value, source_name: sourceName.value })
		availableLines.value = result.lines
		Object.assign(form, {
			supplier: result.supplier,
			supplier_name: result.supplier_name,
			due_date: result.due_date || form.due_date,
			taxes_and_charges: result.taxes_and_charges || "",
			items: result.lines,
		})
	} catch (error) {
		toastError(error)
	} finally {
		loadingLines.value = false
	}
}

function addRemainingLines() {
	const selected = new Set(form.items.map((row) => row.key))
	for (const row of availableLines.value) {
		if (!selected.has(row.key)) form.items.push({ ...row })
	}
}

async function save() {
	saving.value = true
	try {
		const result = await call("create_purchase_invoice", {
			data: {
				source_doctype: sourceDoctype.value,
				source_name: sourceName.value,
				supplier_invoice_no: form.supplier_invoice_no,
				supplier_invoice_date: form.supplier_invoice_date,
				posting_date: form.posting_date,
				due_date: form.due_date,
				remarks: form.remarks,
				taxes_and_charges: form.taxes_and_charges,
				items: form.items.map((row) => ({ key: row.key, qty: row.qty, rate: row.rate, vat: row.vat })),
			},
		})
		toast(`Purchase invoice ${result.name} created as draft`)
		router.push(`/invoices/${result.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

watch(() => form.source, loadLines)

onMounted(async () => {
	await loadSources()
	const preset = route.query.po ? `Purchase Order::${route.query.po}` : route.query.pr ? `Purchase Receipt::${route.query.pr}` : ""
	if (preset) {
		if (!sources.value.some((row) => `${row.doctype}::${row.name}` === preset)) {
			sources.value.unshift({ doctype: preset.split("::")[0], name: preset.split("::")[1], supplier_name: "", per_billed: 0 })
		}
		form.source = preset
	}
})
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader title="New Purchase Invoice" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Purchase Invoices', to: '/invoices' }, { label: 'New' }]">
			<template #actions>
				<RouterLink to="/invoices" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving || !form.items.length">{{ saving ? "Creating…" : "Create invoice" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Invoice</h2>
			<div class="cp-grid-3">
				<label class="cp-field">
					<span>Invoice against<i>*</i></span>
					<select v-model="form.source" class="cp-input" required>
						<option value="">— Select a PO or receive note to bill —</option>
						<optgroup label="Receive notes">
							<option v-for="row in sources.filter((row) => row.doctype === 'Purchase Receipt')" :key="row.name" :value="`${row.doctype}::${row.name}`">
								{{ row.name }} · {{ row.supplier_name }} · {{ Math.round(row.per_billed || 0) }}% billed
							</option>
						</optgroup>
						<optgroup label="Purchase orders">
							<option v-for="row in sources.filter((row) => row.doctype === 'Purchase Order')" :key="row.name" :value="`${row.doctype}::${row.name}`">
								{{ row.name }} · {{ row.supplier_name }} · {{ Math.round(row.per_billed || 0) }}% billed
							</option>
						</optgroup>
					</select>
					<small v-if="selectedSource" class="cp-hint">{{ [selectedSource.project, selectedSource.date && formatDate(selectedSource.date), formatCurrency(selectedSource.grand_total)].filter(Boolean).join(" · ") }}</small>
					<small v-else class="cp-hint">Stock items are normally billed from their receive note; services can be billed from the order.</small>
				</label>
				<label class="cp-field"><span>Supplier</span><input :value="form.supplier_name || form.supplier" class="cp-input" disabled placeholder="From the PO / receive note" /></label>
				<label class="cp-field"><span>Supplier invoice no<i>*</i></span><input v-model="form.supplier_invoice_no" class="cp-input" required placeholder="As printed on their invoice" /></label>
			</div>
			<div class="cp-grid-3">
				<label class="cp-field"><span>Supplier invoice date</span><input v-model="form.supplier_invoice_date" type="date" class="cp-input" /></label>
				<label class="cp-field"><span>Posting date<i>*</i></span><input v-model="form.posting_date" type="date" class="cp-input" required /></label>
				<label class="cp-field"><span>Due date</span><input v-model="form.due_date" type="date" class="cp-input" :min="form.posting_date" /></label>
			</div>
		</section>

		<section v-if="form.source" class="cp-section">
			<div class="cp-section-bar"><h2 class="cp-section-title">Items to bill</h2><button v-if="availableLines.some((row) => !form.items.some((item) => item.key === row.key))" type="button" class="cp-link" @click="addRemainingLines">+ Add source items</button></div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th>Description</th><th>From</th><th class="num">Unbilled</th><th class="num" style="width: 120px">Qty</th><th class="num" style="width: 130px">Rate</th><th style="width: 104px">VAT</th><th class="num">Amount</th><th style="width: 40px" /></tr></thead>
					<tbody>
						<tr v-for="(row, index) in form.items" :key="row.key">
							<td><strong>{{ row.item_name || row.item_code }}</strong><small>{{ [row.item_code, row.project, row.boq_item].filter(Boolean).join(" · ") }}</small></td>
							<td>{{ row.purchase_receipt || row.purchase_order }}</td>
							<td class="num">{{ formatNumber(row.unbilled_qty) }} <span class="cp-muted">{{ row.uom }}</span></td>
							<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0" step="any" :max="row.unbilled_qty" required /></td>
							<td><input v-model.number="row.rate" class="cp-input num" type="number" min="0" step="any" /></td>
							<td><VatSelect v-model="row.vat" /><small class="cp-line-vat">{{ formatCurrency(lineTax(index)) }}</small></td>
							<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0)) }}</td>
							<td><button type="button" class="cp-remove" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
						</tr>
						<tr v-if="loadingLines"><td colspan="8" class="cp-empty-row">Loading unbilled lines…</td></tr>
						<tr v-else-if="!form.items.length"><td colspan="8" class="cp-empty-row">Nothing left to bill on this document.</td></tr>
					</tbody>
					<tfoot v-if="form.items.length"><tr><td colspan="6" class="num">Net total</td><td class="num"><strong>{{ formatCurrency(total) }}</strong></td><td /></tr></tfoot>
				</table>
			</div>
			<p class="cp-hint">Lower a qty to bill part of a line; the rest stays open for a later invoice.</p>
			<TaxSection v-if="form.items.length" v-model="form.taxes_and_charges" :templates="taxTemplates" :totals="totals" :loading="taxLoading" :subtotal="total" />
			<label class="cp-field" style="margin-top: 16px"><span>Remarks</span><textarea v-model="form.remarks" class="cp-input" rows="2" /></label>
		</section>
	</form>
</template>
