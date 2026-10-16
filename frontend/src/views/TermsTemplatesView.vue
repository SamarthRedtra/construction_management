<script setup>
import { onMounted, reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import Modal from "@/components/Modal.vue"
import PageHeader from "@/components/PageHeader.vue"

const rows = ref([])
const editing = ref(false)
const saving = ref(false)
const form = reactive({ name: "", title: "", terms: "", disabled: 0 })

async function load() {
	try { rows.value = await call("get_procurement_terms_templates") } catch (error) { toastError(error) }
}

function open(row = null) {
	Object.assign(form, row ? { name: row.name, title: row.title, terms: row.terms, disabled: row.disabled } : { name: "", title: "", terms: "", disabled: 0 })
	editing.value = true
}

async function save() {
	saving.value = true
	try {
		await call("save_procurement_terms_template", { name: form.name, data: form })
		toast("Terms template saved")
		editing.value = false
		load()
	} catch (error) { toastError(error) } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
	<PageHeader title="LPO terms templates" subtitle="Manage reusable buying terms. Each LPO receives its own editable copy." :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'LPO terms templates' }]">
		<template #actions><button class="cp-btn primary" @click="open()">New template</button></template>
	</PageHeader>
	<section class="cp-card"><table class="cp-table"><thead><tr><th>Title</th><th>Status</th><th /></tr></thead><tbody>
		<tr v-for="row in rows" :key="row.name"><td><strong>{{ row.title }}</strong><small>{{ row.name }}</small></td><td>{{ row.disabled ? 'Disabled' : 'Active' }}</td><td><button class="cp-btn sm" @click="open(row)">Edit</button></td></tr>
		<tr v-if="!rows.length"><td colspan="3" class="cp-empty-row">No buying terms templates.</td></tr>
	</tbody></table></section>
	<Modal v-if="editing" :title="form.name ? 'Edit terms template' : 'New terms template'" wide @close="editing = false"><form id="cp-terms-form" class="cp-stack" @submit.prevent="save"><label class="cp-field"><span>Title<i>*</i></span><input v-model="form.title" class="cp-input" required /></label><label class="cp-field"><span>Terms</span><textarea v-model="form.terms" class="cp-input" rows="14" /></label><label class="cp-check"><input v-model="form.disabled" type="checkbox" :true-value="1" :false-value="0" /> Disable template</label></form><template #footer><button class="cp-btn" @click="editing = false">Cancel</button><button class="cp-btn primary" type="submit" form="cp-terms-form" :disabled="saving">{{ saving ? 'Saving…' : 'Save template' }}</button></template></Modal>
</template>
