<script setup>
import { onMounted, reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { companyFilters, formatCurrency } from "@/utils"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"

const props = defineProps({ purchaseOrder: { type: String, required: true } })
const emit = defineEmits(["close", "created"])
const info = ref(null)
const saving = ref(false)
const form = reactive({ amount: "", mode_of_payment: "", bank_account: "", reference_no: "", reference_date: "" })

onMounted(async () => {
	try {
		info.value = await call("get_po_pdc_defaults", { purchase_order: props.purchaseOrder })
		form.mode_of_payment = info.value.modes[0]?.name || ""
		form.bank_account = info.value.modes[0]?.account || ""
	} catch (error) {
		toastError(error)
		emit("close")
	}
})

function selectMode() {
	form.bank_account = info.value.modes.find((row) => row.name === form.mode_of_payment)?.account || ""
}

async function save() {
	if (saving.value) return
	saving.value = true
	try {
		const result = await call("create_po_pdc", { purchase_order: props.purchaseOrder, data: { ...form } })
		toast(`Post-dated cheque ${result.name} created`)
		emit("created", result)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="`Post-dated cheque — ${purchaseOrder}`" size="lg" @close="emit('close')">
		<div v-if="!info" class="cp-muted">Loading…</div>
		<form v-else id="cp-po-pdc-form" class="cp-stack" @submit.prevent="save">
			<div class="cp-confirm-summary"><span>{{ info.supplier_name }}</span><strong>{{ formatCurrency(info.order_total, info.currency) }} order value</strong></div>
			<p class="cp-banner">This cheque is linked to the Purchase Order, not an invoice. No payment is posted now. If converted before an invoice is allocated, the payment becomes a supplier advance.</p>
			<div class="cp-grid-2">
				<label class="cp-field"><span>Cheque amount<i>*</i></span><input v-model.number="form.amount" class="cp-input num" type="number" min="0.01" step="any" :max="info.order_total" required /></label>
				<label class="cp-field"><span>Mode of payment<i>*</i></span><select v-model="form.mode_of_payment" class="cp-input" required @change="selectMode"><option v-for="mode in info.modes" :key="mode.name" :value="mode.name">{{ mode.name }}</option></select></label>
				<LinkSelect v-model="form.bank_account" doctype="Account" label="Pay from bank" :required="true" :filters="companyFilters({ is_group: 0, account_type: 'Bank' })" />
				<label class="cp-field"><span>Cheque number<i>*</i></span><input v-model="form.reference_no" class="cp-input" required /></label>
				<label class="cp-field"><span>Cheque date<i>*</i></span><input v-model="form.reference_date" class="cp-input" type="date" required /></label>
			</div>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-po-pdc-form" class="cp-btn primary" :disabled="!info || saving || !info.modes.length">{{ saving ? 'Saving…' : 'Create post-dated cheque' }}</button>
		</template>
	</Modal>
</template>
