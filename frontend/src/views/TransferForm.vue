<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { session, today, companyFilters, formatNumber } from "@/utils"
import { useTransferStock } from "@/transferStock"
import ItemPicker from "@/components/ItemPicker.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"

const router = useRouter()
const props = defineProps({ name: { type: String, default: "" } })
const editing = computed(() => Boolean(props.name))
const form = reactive({ company: session.context.default_company || "", posting_date: today(), source_warehouse: "", target_warehouse: "", items: [] })
const saving = ref(false)
const sourceProject = ref("")
const targetProject = ref("")
const { balances, loading: stockLoading, error: stockError, requested, state: stockState, shortage } = useTransferStock(
	computed(() => form.source_warehouse), computed(() => form.items),
)

function addRow() {
	form.items.push({ item_code: "", item_name: "", stock_uom: "", qty: 1, rate: 0 })
}

async function save() {
	saving.value = true
	try {
		const data = { ...form, company: session.context.default_company, items: form.items.map(({ item_code, qty, rate }) => ({ item_code, qty, rate })) }
		const result = editing.value
			? await call("update_material_transfer", { name: props.name, data })
			: await call("create_material_transfer", { data })
		toast(`Material transfer ${result.name} ${editing.value ? "updated" : "created as draft"}`)
		router.push(`/transfers/${result.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

addRow()
watch(() => form.source_warehouse, async (value) => { sourceProject.value = value ? await call("get_warehouse_project", { warehouse: value }) : "" })
watch(() => form.target_warehouse, async (value) => { targetProject.value = value ? await call("get_warehouse_project", { warehouse: value }) : "" })
onMounted(async () => {
	if (!editing.value) return
	try {
		const doc = await call("get_controlled_document", { doctype: "Stock Entry", name: props.name })
		if (doc.docstatus !== 0 || !doc.controlled_procurement) { router.replace(`/transfers/${props.name}`); return }
		Object.assign(form, { company: doc.company, posting_date: String(doc.posting_date).slice(0, 10),
			source_warehouse: doc.from_warehouse || doc.items?.[0]?.s_warehouse || "",
			target_warehouse: doc.to_warehouse || doc.items?.[0]?.t_warehouse || "" })
		form.items = (doc.items || []).map((row) => ({ item_code: row.item_code, item_name: row.item_name, stock_uom: row.stock_uom, qty: row.qty, rate: row.basic_rate || row.valuation_rate || 0 }))
	} catch (error) { toastError(error) }
})
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader :title="editing ? `Edit ${name}` : 'New Material Transfer'" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Material Transfers', to: '/transfers' }, { label: editing ? name : 'New' }]">
			<template #actions>
				<RouterLink :to="editing ? `/transfers/${name}` : '/transfers'" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : editing ? "Save changes" : "Create transfer" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Transfer</h2>
			<div class="cp-grid-3">
				<LinkSelect v-model="form.source_warehouse" doctype="Warehouse" label="From warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
				<LinkSelect v-model="form.target_warehouse" doctype="Warehouse" label="To warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
				<label class="cp-field"><span>Posting date<i>*</i></span><input v-model="form.posting_date" class="cp-input" type="date" required /></label>
			</div>
			<p class="cp-hint">From project: {{ sourceProject || 'General warehouse' }} · To project: {{ targetProject || 'General warehouse' }}. Project attribution follows each warehouse in the stock ledger.</p>
		</section>

		<section class="cp-section">
			<div class="cp-section-bar">
				<h2 class="cp-section-title">Stock items</h2>
				<button type="button" class="cp-link" @click="addRow">+ Add item</button>
			</div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th>Description</th><th class="num" style="width: 140px">Qty</th><th class="num" style="width: 190px">Available now</th><th style="width: 40px" /></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="index">
							<tr>
								<td>
									<ItemPicker v-model="row.item_code" :display-name="row.item_name" :stockable-only="true" @selected="row.item_name = $event.item_name; row.stock_uom = $event.stock_uom" @cleared="row.stock_uom = ''" />
								</td>
								<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0.0001" step="any" required /><small class="cp-muted">{{ row.stock_uom }}</small></td>
								<td class="num">
									<span v-if="stockState(row.item_code) === 'enough'" class="cp-pill success">✓ {{ formatNumber(balances[row.item_code]) }} available</span>
									<span v-else-if="stockState(row.item_code) === 'short'" class="cp-pill danger" role="status" :title="`${formatNumber(requested[row.item_code])} requested across all lines`">! {{ formatNumber(balances[row.item_code]) }} available · short {{ formatNumber(shortage(row.item_code)) }}</span>
									<span v-else class="cp-pill neutral">{{ stockLoading && row.item_code ? 'Checking…' : '—' }}</span>
								</td>
								<td><button type="button" class="cp-remove" :disabled="form.items.length === 1" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
							</tr>
						</template>
					</tbody>
				</table>
			</div>
			<p class="cp-hint">Controlled Stockable and Consumable items can be transferred. Available now is the current physical balance in the From warehouse; stock is checked again on submission.</p>
			<p v-if="stockError" class="cp-hint cp-warn">Could not preview stock: {{ stockError }}</p>
		</section>
	</form>
</template>
