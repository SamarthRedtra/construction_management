<script setup>
import { computed, onMounted, reactive, ref } from "vue"
import { call, printUrl } from "@/api"
import { toastError } from "@/toast"
import Modal from "@/components/Modal.vue"

const props = defineProps({ doctype: { type: String, required: true }, docname: { type: String, required: true } })
const emit = defineEmits(["close"])
const options = ref({ print_formats: ["Standard"], letterheads: [] })
const form = reactive({ print_format: "Standard", letterhead: "" })
const loading = ref(true)

const printLink = computed(() => printUrl(props.doctype, props.docname, form.print_format, false, form.letterhead))
const pdfLink = computed(() => printUrl(props.doctype, props.docname, form.print_format, true, form.letterhead))

onMounted(async () => {
	try {
		options.value = await call("get_print_options", { doctype: props.doctype, name: props.docname })
		form.print_format = options.value.default_print_format
		form.letterhead = options.value.default_letterhead || ""
	} catch (error) {
		toastError(error)
	} finally {
		loading.value = false
	}
})
</script>

<template>
	<Modal :title="`Print ${docname}`" @close="emit('close')">
		<div v-if="loading" class="cp-muted">Loading print formats…</div>
		<div v-else class="cp-stack">
			<label class="cp-field">
				<span>Print format</span>
				<select v-model="form.print_format" class="cp-input">
					<option v-for="format in options.print_formats" :key="format" :value="format">
						{{ format }}{{ format === options.default_print_format ? " (default)" : "" }}
					</option>
				</select>
			</label>
			<label class="cp-field">
				<span>Letterhead</span>
				<select v-model="form.letterhead" class="cp-input">
					<option value="">No letterhead</option>
					<option v-for="letterhead in options.letterheads" :key="letterhead" :value="letterhead">{{ letterhead }}</option>
				</select>
			</label>
		</div>
		<template #footer>
			<button type="button" class="cp-btn" @click="emit('close')">Cancel</button>
			<a class="cp-btn" :href="pdfLink" target="_blank" @click="emit('close')">Download PDF</a>
			<a class="cp-btn primary" :href="printLink" target="_blank" @click="emit('close')">Print</a>
		</template>
	</Modal>
</template>
