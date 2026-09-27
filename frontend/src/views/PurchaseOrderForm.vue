<script setup>
import { computed, nextTick, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { companyFilters, formatCurrency, session, today } from "@/utils"
import AllocationFields from "@/components/AllocationFields.vue"
import ContactDialog from "@/components/ContactDialog.vue"
import ItemPicker from "@/components/ItemPicker.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import TaxSection from "@/components/TaxSection.vue"
import VatSelect from "@/components/VatSelect.vue"
import { useTaxes } from "@/taxes"

const router = useRouter()
const form = reactive({ company: session.context.default_company || "", supplier: "", required_by: today(), warehouse: "", contact_person: "", tc_name: "", terms: "", taxes_and_charges: null, project: "", bill_no: "", boq_item: "", items: [] })
const saving = ref(false)
const total = computed(() => form.items.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))
const { templates: taxTemplates, totals, loading: taxLoading, lineTax } = useTaxes("Purchase Order", form)

const contacts = ref([])
const contactDialog = ref(null) // null = closed, {} = new, contact = edit
const termsEditor = ref(null)
const selectedContact = computed(() => contacts.value.find((row) => row.name === form.contact_person))

async function loadContacts(preferred = "") {
	contacts.value = form.supplier ? await call("get_supplier_contacts", { supplier: form.supplier }) : []
	const keep = preferred || form.contact_person
	form.contact_person = contacts.value.some((row) => row.name === keep) ? keep : contacts.value[0]?.name || ""
}

function onContactSaved(contact) {
	contactDialog.value = null
	loadContacts(contact.name)
}

async function applyTerms() {
	const html = form.tc_name ? await call("get_terms_template", { template: form.tc_name }) : ""
	form.terms = html
	await nextTick()
	if (termsEditor.value) termsEditor.value.innerHTML = html
}

watch(() => form.supplier, () => {
	form.contact_person = ""
	loadContacts().catch(toastError)
})
watch(() => form.tc_name, () => applyTerms().catch(toastError))

function addRow() {
	form.items.push({ item_code: "", controlled_item_type: "", qty: 1, rate: 0, vat: "standard", notes: "", use_override: false, project: "", bill_no: "", boq_item: "" })
}

async function save() {
	saving.value = true
	try {
		const result = await call("create_purchase_order", { data: { ...form, terms: termsEditor.value?.innerHTML || form.terms } })
		toast(`Purchase order ${result.name} created as draft`)
		router.push(`/purchase-orders/${result.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

addRow()
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader title="New Purchase Order" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Purchase Orders', to: '/purchase-orders' }, { label: 'New' }]">
			<template #actions>
				<RouterLink to="/purchase-orders" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving">{{ saving ? "Creating…" : "Create order" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Order</h2>
			<div class="cp-grid-3">
				<LinkSelect v-model="form.supplier" doctype="Supplier" label="Supplier" :required="true" />
				<label class="cp-field"><span>Company</span><input :value="form.company" class="cp-input" disabled title="Switch company from the top bar" /></label>
				<label class="cp-field"><span>Required by<i>*</i></span><input v-model="form.required_by" type="date" class="cp-input" required /></label>
			</div>
			<div class="cp-grid-3">
				<div>
					<LinkSelect v-model="form.warehouse" doctype="Warehouse" label="Deliver to warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
					<small class="cp-hint">Where the supplier should deliver. Used for every line.</small>
				</div>
				<div class="cp-field">
					<span>Contact person</span>
					<div class="cp-inline-input">
						<select v-model="form.contact_person" class="cp-input" :disabled="!form.supplier">
							<option value="">{{ !form.supplier ? "Select a supplier first" : contacts.length ? "— No contact —" : "No contacts on this supplier" }}</option>
							<option v-for="contact in contacts" :key="contact.name" :value="contact.name">{{ contact.full_name || contact.name }}{{ contact.designation ? ` · ${contact.designation}` : "" }}</option>
						</select>
						<button type="button" class="cp-link" :disabled="!form.supplier" @click="contactDialog = {}">+ New</button>
					</div>
				</div>
				<div v-if="selectedContact" class="cp-contact-card">
					<div>
						<strong>{{ selectedContact.full_name }}</strong>
						<small>{{ selectedContact.email_id || "No email" }} · {{ selectedContact.mobile_no || selectedContact.phone || "No phone" }}</small>
						<small v-if="!selectedContact.email_id" class="cp-overdue">Add an email so the LPO can be sent to this person.</small>
					</div>
					<button type="button" class="cp-btn sm" @click="contactDialog = selectedContact">Edit</button>
				</div>
			</div>
			<AllocationFields :model-value="{ project: form.project, bill_no: form.bill_no, boq_item: form.boq_item }" @update:model-value="Object.assign(form, $event)" />
		</section>

		<section class="cp-section">
			<div class="cp-section-bar">
				<h2 class="cp-section-title">Items</h2>
				<button type="button" class="cp-link" @click="addRow">+ Add item</button>
			</div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th style="width: 30%">Description</th><th>Notes</th><th class="num" style="width: 100px">Qty</th><th style="width: 60px">UOM</th><th class="num" style="width: 120px">Rate</th><th style="width: 104px">VAT</th><th class="num" style="width: 140px">Amount</th><th style="width: 40px" /></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="index">
							<tr>
								<td>
									<ItemPicker v-model="row.item_code" @selected="row.controlled_item_type = $event.controlled_item_type" />
									<button type="button" class="cp-link sm" @click="row.use_override = !row.use_override">{{ row.use_override ? "Use order allocation" : "Different project / BOQ for this line" }}</button>
								</td>
								<td><input v-model="row.notes" class="cp-input" placeholder="Notes…" /></td>
								<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0.0001" step="any" required /></td>
								<td><span class="cp-muted">Nos</span></td>
								<td><input v-model.number="row.rate" class="cp-input num" type="number" min="0" step="any" /></td>
								<td><VatSelect v-model="row.vat" /><small class="cp-line-vat">{{ formatCurrency(lineTax(index)) }}</small></td>
								<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0)) }}</td>
								<td><button type="button" class="cp-remove" :disabled="form.items.length === 1" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
							</tr>
							<tr v-if="row.use_override" class="cp-subrow">
								<td colspan="8"><AllocationFields :model-value="row" @update:model-value="Object.assign(row, $event)" /></td>
							</tr>
						</template>
					</tbody>
					<tfoot><tr><td colspan="6" class="num">Net total</td><td class="num"><strong>{{ formatCurrency(total) }}</strong></td><td /></tr></tfoot>
				</table>
			</div>
			<p class="cp-hint">Only approved controlled catalog items with UOM Nos can be ordered.</p>
			<TaxSection v-model="form.taxes_and_charges" :templates="taxTemplates" :totals="totals" :loading="taxLoading" :subtotal="total" />
		</section>

		<section class="cp-section">
			<h2 class="cp-section-title">Terms &amp; conditions</h2>
			<div class="cp-grid-3">
				<LinkSelect v-model="form.tc_name" doctype="Terms and Conditions" label="Terms template" placeholder="Select a template" :filters="{ buying: 1, disabled: 0 }" />
			</div>
			<div class="cp-field" style="margin-top: 16px">
				<span>Terms <small class="cp-muted">(edit as needed for this order)</small></span>
				<div ref="termsEditor" class="cp-input cp-editor" contenteditable="true" data-placeholder="Pick a template or type the terms for this order" />
			</div>
		</section>
		<ContactDialog v-if="contactDialog" :supplier="form.supplier" :contact="contactDialog.name ? contactDialog : null" @close="contactDialog = null" @saved="onContactSaved" />
	</form>
</template>
