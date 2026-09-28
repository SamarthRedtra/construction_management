<script setup>
import { computed, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { formatCurrency, formatNumber } from "@/utils"
import ItemPicker from "@/components/ItemPicker.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"
import VatSelect from "@/components/VatSelect.vue"
import { VAT_LABELS } from "@/utils"

const props = defineProps({ doc: { type: Object, required: true } })
const emit = defineEmits(["close", "updated"])
const rows = ref(
	props.doc.items.map((row) => ({
		docname: row.name,
		item_code: row.item_code,
		item_name: row.item_name,
		uom: row.uom,
		qty: row.qty,
		rate: row.rate,
		vat: row.vat || "standard",
		received_qty: row.received_qty || 0,
		billed: (row.billed_amt || 0) > 0,
	})),
)
const saving = ref(false)
const controlled = Boolean(props.doc.controlled_procurement)
const total = computed(() => rows.value.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))

function addRow() {
	rows.value.push({ docname: null, item_code: "", item_name: "", uom: "", qty: 1, rate: 0, vat: "standard", received_qty: 0, billed: false })
}

async function save() {
	saving.value = true
	try {
		await call("update_purchase_order_items", {
			name: props.doc.name,
			items: rows.value.filter((row) => row.item_code).map(({ docname, item_code, qty, rate, uom, vat }) => ({ docname, item_code, qty, rate, uom, vat })),
		})
		toast(`${props.doc.name} updated`)
		emit("updated")
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="`Update items — ${doc.name}`" size="xl" @close="emit('close')">
		<p class="cp-hint" style="margin: 0 0 12px">
			Change quantities or rates, add lines, or remove lines that have not been received. A line cannot go below what has already been received.
			<template v-if="doc.custom_is_provisional_po"> This is an <strong>Open PO</strong>: receive notes larger than the ordered qty also raise it automatically.</template>
		</p>
		<form id="cp-update-items" @submit.prevent="save">
			<div class="cp-card" style="margin: 0">
				<table class="cp-table cp-edit-table cp-fixed-table">
					<colgroup><col /><col style="width: 100px" /><col style="width: 140px" /><col style="width: 140px" /><col style="width: 110px" /><col style="width: 160px" /><col style="width: 52px" /></colgroup>
					<thead><tr><th>Description</th><th class="num">Received</th><th class="num">Qty</th><th class="num">Rate</th><th>VAT</th><th class="num">Amount</th><th /></tr></thead>
					<tbody>
						<tr v-for="(row, index) in rows" :key="row.docname || `new-${index}`">
							<td>
								<template v-if="row.docname"><strong>{{ row.item_name || row.item_code }}</strong><small>{{ row.item_code }} · {{ row.uom }}</small></template>
								<ItemPicker v-else-if="controlled" v-model="row.item_code" />
								<LinkSelect v-else v-model="row.item_code" doctype="Item" placeholder="Select item" :filters="{ is_purchase_item: 1, disabled: 0 }" />
							</td>
							<td class="num">{{ formatNumber(row.received_qty) }}</td>
							<td><input v-model.number="row.qty" class="cp-input num" type="number" step="any" :min="Math.max(row.received_qty, 0.0001)" required /></td>
							<td><input v-model.number="row.rate" class="cp-input num" type="number" step="any" min="0" :disabled="row.billed" :title="row.billed ? 'Already billed — rate is locked' : ''" /></td>
							<td>
								<VatSelect v-if="!row.docname" v-model="row.vat" />
								<span v-else class="cp-muted" title="Existing lines keep their VAT">{{ VAT_LABELS[row.vat] }}</span>
							</td>
							<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0), doc.currency) }}</td>
							<td>
								<button type="button" class="cp-remove" :disabled="row.received_qty > 0 || rows.length === 1" :title="row.received_qty > 0 ? 'Received lines cannot be removed' : 'Remove line'" @click="rows.splice(index, 1)">×</button>
							</td>
						</tr>
					</tbody>
					<tfoot><tr><td colspan="5" class="num">Total before tax</td><td class="num"><strong>{{ formatCurrency(total, doc.currency) }}</strong></td><td /></tr></tfoot>
				</table>
			</div>
			<button type="button" class="cp-link" style="margin-top: 12px" @click="addRow">+ Add item</button>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-update-items" class="cp-btn primary" :disabled="saving">{{ saving ? "Updating…" : "Update items" }}</button>
		</template>
	</Modal>
</template>
