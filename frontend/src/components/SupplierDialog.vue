<script setup>
import { reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import LinkSelect from "@/components/LinkSelect.vue"
import Modal from "@/components/Modal.vue"

const emit = defineEmits(["close", "saved"])
const props = defineProps({ supplier: { type: String, default: "" } })
const form = reactive({
	supplier_name: "", supplier_group: "", supplier_type: "Company", tax_id: "", trade_licence_no: "",
	po_box_no: "", payment_terms: "", contact_first_name: "", contact_last_name: "",
	contact_email: "", contact_mobile: "", address_line1: "", address_line2: "",
	city: "", state: "", pincode: "", country: "",
})
const saving = ref(false)

if (props.supplier) {
	call("get_supplier_profile", { supplier: props.supplier })
		.then((result) => { Object.assign(form, result) })
		.catch(toastError)
}

async function save() {
	saving.value = true
	try {
		const supplier = props.supplier
			? await call("update_supplier_profile", { supplier: props.supplier, data: form })
			: await call("create_supplier", { data: form })
		toast(props.supplier ? "Supplier profile updated" : "Supplier created")
		emit("saved", supplier)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="supplier ? 'Edit supplier' : 'New supplier'" size="lg" @close="emit('close')">
		<form id="cp-supplier-form" class="cp-stack" @submit.prevent="save">
			<label class="cp-field"><span>Supplier Name<i>*</i></span><input v-model="form.supplier_name" class="cp-input" required autofocus /></label>
			<label class="cp-field"><span>Supplier Type<i>*</i></span><select v-model="form.supplier_type" class="cp-input" required><option>Company</option><option>Individual</option><option>Partnership</option></select></label>
			<label class="cp-field"><span>TRN No</span><input v-model="form.tax_id" class="cp-input" /></label>
			<label class="cp-field"><span>Trade Licence No</span><input v-model="form.trade_licence_no" class="cp-input" /></label>
			<label class="cp-field"><span>PO Box no</span><input v-model="form.po_box_no" class="cp-input" /></label>
			<div class="cp-supplier-section"><h3>Primary Contact Details</h3>
				<div class="cp-grid-2">
					<label class="cp-field"><span>First Name</span><input v-model="form.contact_first_name" class="cp-input" /></label>
					<label class="cp-field"><span>Email Id</span><input v-model="form.contact_email" type="email" class="cp-input" /></label>
					<label class="cp-field"><span>Last Name</span><input v-model="form.contact_last_name" class="cp-input" /></label>
					<label class="cp-field"><span>Mobile Number</span><input v-model="form.contact_mobile" type="tel" class="cp-input" /></label>
				</div>
			</div>
			<div class="cp-supplier-section"><h3>Primary Address Details</h3>
				<div class="cp-grid-2">
					<label class="cp-field"><span>Address Line 1</span><input v-model="form.address_line1" class="cp-input" /></label>
					<label class="cp-field"><span>City</span><input v-model="form.city" class="cp-input" /></label>
					<label class="cp-field"><span>Address Line 2</span><input v-model="form.address_line2" class="cp-input" /></label>
					<label class="cp-field"><span>State/Province</span><input v-model="form.state" class="cp-input" /></label>
					<label class="cp-field"><span>ZIP Code</span><input v-model="form.pincode" class="cp-input" /></label>
					<LinkSelect v-model="form.country" doctype="Country" label="Country" />
				</div>
			</div>
			<div class="cp-supplier-section"><h3>Purchasing Defaults</h3>
				<div class="cp-grid-2">
					<LinkSelect v-model="form.supplier_group" doctype="Supplier Group" label="Supplier group" :filters="{ is_group: 0 }" />
					<LinkSelect v-model="form.payment_terms" doctype="Payment Terms Template" label="Default payment terms" placeholder="Select payment terms" />
				</div>
			</div>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-supplier-form" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : supplier ? "Save supplier" : "Create supplier" }}</button>
		</template>
	</Modal>
</template>

<style scoped>
.cp-supplier-section { border-top: 1px solid var(--border); padding-top: 12px; }
.cp-supplier-section h3 { margin: 0 0 12px; font-size: 14px; font-weight: 600; }
</style>
