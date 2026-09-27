<script setup>
import { reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import Modal from "@/components/Modal.vue"

const props = defineProps({
	supplier: { type: String, required: true },
	contact: { type: Object, default: null },
})
const emit = defineEmits(["close", "saved"])
const form = reactive({
	name: props.contact?.name || "",
	first_name: props.contact?.first_name || "",
	last_name: props.contact?.last_name || "",
	designation: props.contact?.designation || "",
	email_id: props.contact?.email_id || "",
	phone: props.contact?.phone || "",
	mobile_no: props.contact?.mobile_no || "",
})
const saving = ref(false)

async function save() {
	saving.value = true
	try {
		const contact = await call("save_supplier_contact", { supplier: props.supplier, data: form })
		toast(form.name ? "Contact updated" : "Contact created")
		emit("saved", contact)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}
</script>

<template>
	<Modal :title="form.name ? 'Edit contact person' : 'New contact person'" wide @close="emit('close')">
		<form id="cp-contact-form" class="cp-stack" @submit.prevent="save">
			<p class="cp-hint" style="margin: 0">Saved on the supplier <strong>{{ supplier }}</strong>, so it is correct for future orders too.</p>
			<div class="cp-grid-2">
				<label class="cp-field"><span>First name<i>*</i></span><input v-model="form.first_name" class="cp-input" required /></label>
				<label class="cp-field"><span>Last name</span><input v-model="form.last_name" class="cp-input" /></label>
				<label class="cp-field"><span>Designation</span><input v-model="form.designation" class="cp-input" placeholder="e.g. Sales Manager" /></label>
				<label class="cp-field"><span>Email</span><input v-model="form.email_id" class="cp-input" type="email" placeholder="name@supplier.com" /></label>
				<label class="cp-field"><span>Mobile</span><input v-model="form.mobile_no" class="cp-input" /></label>
				<label class="cp-field"><span>Phone</span><input v-model="form.phone" class="cp-input" /></label>
			</div>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-contact-form" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : "Save contact" }}</button>
		</template>
	</Modal>
</template>
