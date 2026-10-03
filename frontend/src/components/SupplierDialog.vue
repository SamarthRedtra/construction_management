<script setup>
import { reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"

const emit = defineEmits(["close", "saved"])
const props = defineProps({ supplier: { type: String, default: "" } })
const form = reactive({ supplier_name: "", supplier_group: "", supplier_type: "Company", tax_id: "", payment_terms: "" })
const saving = ref(false)

if (props.supplier) {
	call("get_supplier_payment_terms", { supplier: props.supplier })
		.then((result) => { form.payment_terms = result.payment_terms || "" })
		.catch(toastError)
}

async function save() {
	saving.value = true
	try {
		const supplier = props.supplier
			? await call("set_supplier_payment_terms", { supplier: props.supplier, payment_terms: form.payment_terms })
			: await call("create_supplier", { data: form })
		toast(props.supplier ? "Supplier payment terms updated" : "Supplier created")
		emit("saved", supplier)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="supplier ? 'Edit supplier payment terms' : 'New supplier'" @close="emit('close')">
		<form id="cp-supplier-form" class="cp-stack" @submit.prevent="save">
			<template v-if="!supplier">
				<label class="cp-field"><span>Supplier name<i>*</i></span><input v-model="form.supplier_name" class="cp-input" required autofocus /></label>
				<LinkSelect v-model="form.supplier_group" doctype="Supplier Group" label="Supplier group" :filters="{ is_group: 0 }" />
				<label class="cp-field"><span>Supplier type<i>*</i></span><select v-model="form.supplier_type" class="cp-input" required><option>Company</option><option>Individual</option><option>Partnership</option></select></label>
				<label class="cp-field"><span>Tax ID</span><input v-model="form.tax_id" class="cp-input" placeholder="VAT / TRN / Tax number" /></label>
			</template>
			<p v-else class="cp-hint">{{ supplier }}</p>
			<LinkSelect v-model="form.payment_terms" doctype="Payment Terms Template" label="Default payment terms" placeholder="Select payment terms" />
			<p class="cp-hint">This becomes the default for future orders; each order can still use different terms.</p>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-supplier-form" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : supplier ? "Save terms" : "Create supplier" }}</button>
		</template>
	</Modal>
</template>
