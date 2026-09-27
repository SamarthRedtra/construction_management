<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { companyFilters, formatCurrency, today } from "@/utils"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"

const props = defineProps({ invoice: { type: String, required: true } })
const emit = defineEmits(["close", "paid"])
const info = ref(null)
const saving = ref(false)
const form = reactive({ amount: 0, mode_of_payment: "", account: "", reference_no: "", reference_date: today(), posting_date: today(), remarks: "" })

const mode = computed(() => info.value?.modes.find((row) => row.name === form.mode_of_payment))
const isCheque = computed(() => /cheque/i.test(form.mode_of_payment))
const postDated = computed(() => isCheque.value && form.reference_date > today())
const reserved = computed(() => (info.value ? info.value.outstanding_amount - info.value.payable_amount : 0))

function onModeChange() {
	if (mode.value?.account) form.account = mode.value.account
}

onMounted(async () => {
	try {
		info.value = await call("get_payment_defaults", { invoice: props.invoice })
		form.amount = info.value.payable_amount
		const preferred = info.value.modes.find((row) => row.name === "Wire Transfer") || info.value.modes.find((row) => row.type === "Bank") || info.value.modes[0]
		form.mode_of_payment = preferred?.name || ""
		onModeChange()
	} catch (error) {
		toastError(error)
		emit("close")
	}
})

async function save() {
	saving.value = true
	try {
		const result = await call("record_invoice_payment", { invoice: props.invoice, data: { ...form } })
		toast(result.post_dated ? `Post-dated cheque ${result.name} recorded` : `Payment ${result.name} recorded`)
		emit("paid", result)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="`Record payment — ${invoice}`" size="lg" @close="emit('close')">
		<div v-if="!info" class="cp-muted">Loading…</div>
		<form v-else id="cp-payment-form" class="cp-stack" @submit.prevent="save">
			<div class="cp-confirm-summary">
				<span>{{ info.supplier_name }}<template v-if="info.supplier_invoice_no"> · {{ info.supplier_invoice_no }}</template></span>
				<strong>{{ formatCurrency(info.outstanding_amount, info.currency) }} outstanding</strong>
			</div>
			<p v-if="reserved > 0.01" class="cp-hint cp-warn">{{ formatCurrency(reserved, info.currency) }} is already covered by pending post-dated cheques.</p>
			<div class="cp-grid-2">
				<label class="cp-field">
					<span>Amount<i>*</i></span>
					<input v-model.number="form.amount" class="cp-input num" type="number" min="0.01" step="any" :max="info.payable_amount" required />
				</label>
				<label class="cp-field">
					<span>Mode of payment<i>*</i></span>
					<select v-model="form.mode_of_payment" class="cp-input" required @change="onModeChange">
						<option v-for="row in info.modes" :key="row.name" :value="row.name">{{ row.name }}</option>
					</select>
				</label>
				<LinkSelect v-model="form.account" doctype="Account" :label="mode?.type === 'Cash' ? 'Pay from (cash)' : 'Pay from (bank)'" :required="true" :filters="companyFilters({ is_group: 0, account_type: ['in', ['Bank', 'Cash']] })" />
				<label class="cp-field">
					<span>{{ isCheque ? "Cheque no" : "Reference no" }}<i v-if="isCheque">*</i></span>
					<input v-model="form.reference_no" class="cp-input" :required="isCheque" :placeholder="isCheque ? '' : 'Transfer ref (optional)'" />
				</label>
				<label class="cp-field"><span>{{ isCheque ? "Cheque date" : "Reference date" }}</span><input v-model="form.reference_date" type="date" class="cp-input" /></label>
				<label v-if="!postDated" class="cp-field"><span>Posting date</span><input v-model="form.posting_date" type="date" class="cp-input" /></label>
			</div>
			<p v-if="postDated" class="cp-banner">This cheque is dated in the future, so it will be recorded as a <strong>post-dated cheque</strong> against this invoice and paid out on its date.</p>
			<label class="cp-field"><span>Remarks</span><input v-model="form.remarks" class="cp-input" /></label>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-payment-form" class="cp-btn primary" :disabled="!info || saving">
				{{ saving ? "Saving…" : postDated ? "Record post-dated cheque" : "Record payment" }}
			</button>
		</template>
	</Modal>
</template>
