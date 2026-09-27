<script setup>
import { nextTick, onMounted, reactive, ref } from "vue"
import { call, printUrl } from "@/api"
import { toast, toastError } from "@/toast"
import Modal from "@/components/Modal.vue"

const props = defineProps({ doctype: { type: String, required: true }, docname: { type: String, required: true } })
const emit = defineEmits(["close", "sent"])
const form = reactive({ email_template: "", recipients: "", cc: "", subject: "", attach_print: true, print_format: "Standard" })
const printFormats = ref(["Standard"])
const templates = ref([])
const editor = ref(null)
const loading = ref(true)
const applying = ref(false)
const sending = ref(false)
const showCc = ref(false)

function setBody(html) {
	if (editor.value) editor.value.innerHTML = html || ""
}

onMounted(async () => {
	try {
		const draft = await call("get_email_draft", { doctype: props.doctype, name: props.docname })
		Object.assign(form, { recipients: draft.recipients, subject: draft.subject, print_format: draft.default_print_format })
		printFormats.value = draft.print_formats
		templates.value = draft.email_templates || []
		loading.value = false
		await nextTick()
		setBody(draft.message)
	} catch (error) {
		toastError(error)
		loading.value = false
	}
})

async function applyTemplate() {
	if (!form.email_template) return
	applying.value = true
	try {
		const rendered = await call("get_rendered_email_template", { doctype: props.doctype, name: props.docname, template: form.email_template })
		if (rendered.subject) form.subject = rendered.subject
		setBody(rendered.message)
	} catch (error) {
		toastError(error)
	} finally {
		applying.value = false
	}
}

async function send() {
	sending.value = true
	try {
		const result = await call("send_document_email", {
			doctype: props.doctype,
			name: props.docname,
			recipients: form.recipients,
			cc: form.cc,
			subject: form.subject,
			message: editor.value?.innerHTML || "",
			attach_print: form.attach_print ? 1 : 0,
			print_format: form.print_format,
			email_template: form.email_template,
		})
		toast(result.emails_not_sent_to ? `Sent, except to ${result.emails_not_sent_to}` : "Email queued for sending")
		emit("sent")
	} catch (error) {
		toastError(error)
	} finally {
		sending.value = false
	}
}
</script>

<template>
	<Modal :title="`Email ${doctype}`" wide @close="emit('close')">
		<div v-if="loading" class="cp-muted">Preparing email…</div>
		<form v-else id="cp-email-form" class="cp-stack" @submit.prevent="send">
			<label class="cp-field">
				<span>Email template</span>
				<select v-model="form.email_template" class="cp-input" :disabled="applying" @change="applyTemplate">
					<option value="">{{ templates.length ? "— No template (write your own) —" : "No email templates set up for this document" }}</option>
					<option v-for="template in templates" :key="template" :value="template">{{ template }}</option>
				</select>
			</label>
			<label class="cp-field">
				<span>To<i>*</i></span>
				<div class="cp-inline-input">
					<input v-model="form.recipients" class="cp-input" placeholder="supplier@example.com, other@example.com" required />
					<button v-if="!showCc" type="button" class="cp-link" @click="showCc = true">Cc</button>
				</div>
				<small v-if="!form.recipients" class="cp-hint">No email on the supplier record — enter one manually.</small>
			</label>
			<label v-if="showCc" class="cp-field"><span>Cc</span><input v-model="form.cc" class="cp-input" /></label>
			<label class="cp-field"><span>Subject<i>*</i></span><input v-model="form.subject" class="cp-input" required /></label>
			<div class="cp-field">
				<span>Message</span>
				<div ref="editor" class="cp-input cp-editor" contenteditable="true" />
			</div>
			<div class="cp-attach-row">
				<label class="cp-check"><input v-model="form.attach_print" type="checkbox" /> Attach PDF</label>
				<select v-if="form.attach_print" v-model="form.print_format" class="cp-input cp-input-sm">
					<option v-for="format in printFormats" :key="format" :value="format">{{ format }}</option>
				</select>
				<a v-if="form.attach_print" class="cp-link" :href="printUrl(doctype, docname, form.print_format)" target="_blank">Preview</a>
			</div>
		</form>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<button type="submit" form="cp-email-form" class="cp-btn primary" :disabled="loading || sending || applying">{{ sending ? "Sending…" : "Send email" }}</button>
		</template>
	</Modal>
</template>
