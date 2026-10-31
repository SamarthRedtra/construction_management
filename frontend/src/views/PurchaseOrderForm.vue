<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { companyFilters, formatCurrency, session, today } from "@/utils"
import AllocationFields from "@/components/AllocationFields.vue"
import ContactDialog from "@/components/ContactDialog.vue"
import ItemPicker from "@/components/ItemPicker.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"
import SupplierDialog from "@/components/SupplierDialog.vue"
import TaxSection from "@/components/TaxSection.vue"
import VatSelect from "@/components/VatSelect.vue"
import { useTaxes } from "@/taxes"

const router = useRouter()
const route = useRoute()
const props = defineProps({ name: { type: String, default: "" } })
const editing = computed(() => Boolean(props.name))
const duplicateSource = computed(() => (editing.value ? "" : String(route.query.duplicate || "")))
const form = reactive({ company: session.context.default_company || "", supplier: "", order_date: today(), required_by: today(), lpo_type: !editing.value && route.query.lpo_type === "Open" ? "Open" : "Standard", warehouse: "", contact_person: "", payment_terms_template: "", tc_name: "", terms: "", taxes_and_charges: null, apply_discount_on: "Net Total", additional_discount_percentage: 0, discount_amount: 0, project: "", bill_no: "", boq_item: "", items: [] })
const saving = ref(false)
const createdOrderName = ref("")
const priceApprovalStatus = ref("")
const hydrating = ref(false)
const total = computed(() => form.items.reduce((sum, row) => sum + (Number(row.qty) || 0) * (Number(row.rate) || 0), 0))
const { templates: taxTemplates, totals, loading: taxLoading, lineTax } = useTaxes("Purchase Order", form)

const contacts = ref([])
const contactDialog = ref(null) // null = closed, {} = new, contact = edit
const supplierDialog = ref(false)
const editSupplierTerms = ref(false)
const termsEditor = ref(null)
const selectedContact = computed(() => contacts.value.find((row) => row.name === form.contact_person))
const eligibleSuppliers = ref([])
const supplierChoiceItem = ref("")
const itemSupplierLoading = ref(false)
const itemSupplierMessage = ref("")
const allocationFields = ["project", "bill_no", "boq_item"]
const emptyAllocationValues = new Set(["", "null", "undefined"])

async function loadContacts(preferred = "") {
	contacts.value = form.supplier ? await call("get_supplier_contacts", { supplier: form.supplier }) : []
	const keep = preferred || form.contact_person
	form.contact_person = contacts.value.some((row) => row.name === keep) ? keep : contacts.value[0]?.name || ""
}

function onContactSaved(contact) {
	contactDialog.value = null
	loadContacts(contact.name)
}

function onSupplierSaved(supplier) {
	supplierDialog.value = false
	editSupplierTerms.value = false
	form.supplier = supplier.name
	form.payment_terms_template = supplier.payment_terms || ""
}

async function loadSupplierTerms(supplier) {
	const terms = supplier ? (await call("get_supplier_payment_terms", { supplier })).payment_terms || "" : ""
	if (form.supplier === supplier) form.payment_terms_template = terms
}

async function loadBuyingPrice(row, { keepRateIfMissing = false } = {}) {
	const code = row.item_code
	const supplier = form.supplier
	if (!code || !supplier) return
	const revision = (row.price_request_id || 0) + 1
	row.price_request_id = revision
	row.price_loading = true
	try {
		const price = await call("get_catalog_buying_price", { item_code: code, supplier, company: session.context.default_company || form.company, order_date: form.order_date })
		if (row.price_request_id === revision && row.item_code === code && form.supplier === supplier && !row.rate_edited) {
			if (price.rate != null) {
				row.rate = price.rate
				row.price_missing = false
				row.fetched_rate = price.rate
				row.fetched_item_price = price.item_price || ""
			} else if (keepRateIfMissing && Number(row.rate) > 0) {
				// Order date changed but no Item Price for that date — keep the loaded rate.
				row.price_missing = false
			} else {
				row.rate = 0
				row.price_missing = true
				row.fetched_rate = null
				row.fetched_item_price = ""
			}
		}
	} catch (error) {
		if (row.price_request_id === revision) toastError(error)
	} finally {
		if (row.price_request_id === revision) row.price_loading = false
	}
}

function resetRate(row) {
	row.price_request_id = (row.price_request_id || 0) + 1
	row.rate = 0
	row.rate_edited = false
	row.fetched_rate = null
	row.fetched_item_price = ""
	row.price_change_reason = ""
	row.price_loading = false
	row.price_missing = false
}

async function lookupItemSuppliers(row) {
	const code = row.item_code
	const revision = (row.supplier_lookup_id || 0) + 1
	row.supplier_lookup_id = revision
	itemSupplierLoading.value = true
	try {
		const suppliers = await call("get_catalog_item_suppliers", { item_code: code, company: session.context.default_company || form.company })
		if (row.supplier_lookup_id !== revision || row.item_code !== code || form.supplier) return
		eligibleSuppliers.value = suppliers
		supplierChoiceItem.value = suppliers.length > 1 ? code : ""
		if (suppliers.length === 1) form.supplier = suppliers[0].name
		else if (!suppliers.length) itemSupplierMessage.value = "This item has no available linked supplier. Link one through a catalog request before ordering."
	} catch (error) {
		if (row.supplier_lookup_id === revision) toastError(error)
	} finally {
		if (row.supplier_lookup_id === revision) itemSupplierLoading.value = false
	}
}

async function selectItem(row, item) {
	if (row.item_code !== item.name) row.docname = null
	row.item_code = item.name
	row.item_name = item.item_name
	row.controlled_item_type = item.controlled_item_type
	row.controlled_procurement_catalog = item.controlled_procurement_catalog == null ? 1 : Number(item.controlled_procurement_catalog)
	row.stock_uom = item.stock_uom
	row.notes = item.item_name
	row.not_in_catalog = false
	resetRate(row)
	itemSupplierMessage.value = ""
	eligibleSuppliers.value = []
	supplierChoiceItem.value = ""
	if (form.supplier) loadBuyingPrice(row)
	else lookupItemSuppliers(row)
}

function clearItem(row, message = "") {
	row.supplier_lookup_id = (row.supplier_lookup_id || 0) + 1
	row.docname = null
	row.item_code = ""
	row.item_name = ""
	row.controlled_item_type = ""
	row.controlled_procurement_catalog = 0
	row.stock_uom = ""
	row.notes = ""
	row.not_in_catalog = false
	resetRate(row)
	eligibleSuppliers.value = []
	supplierChoiceItem.value = ""
	itemSupplierLoading.value = false
	itemSupplierMessage.value = message
}

let supplierRevision = 0
async function checkSelectedItemsForSupplier(supplier) {
	const revision = ++supplierRevision
	for (const row of form.items.filter((item) => item.item_code)) {
		const code = row.item_code
		try {
			const result = await call("get_catalog_supplier_match", { item_code: code, supplier })
			if (revision !== supplierRevision || row.item_code !== code || form.supplier !== supplier) continue
			if (!result.eligible) {
				clearItem(row, `The selected item is not linked to ${supplier}. Choose one of this supplier's items.`)
				continue
			}
			loadBuyingPrice(row)
		} catch (error) {
			if (revision === supplierRevision) toastError(error)
		}
	}
}

async function applyTerms() {
	const html = form.tc_name ? await call("get_terms_template", { template: form.tc_name }) : ""
	form.terms = html
	await nextTick()
	if (termsEditor.value) termsEditor.value.innerHTML = html
}

watch(() => form.supplier, (supplier, previous) => {
	if (hydrating.value) return
	form.contact_person = ""
	loadContacts().catch(toastError)
	loadSupplierTerms(form.supplier).catch(toastError)
	if (supplier === previous) return
	itemSupplierMessage.value = ""
	eligibleSuppliers.value = []
	supplierChoiceItem.value = ""
	for (const row of form.items.filter((item) => item.item_code)) resetRate(row)
	if (!supplier) {
		for (const row of form.items.filter((item) => item.item_code)) lookupItemSuppliers(row)
	} else if (form.lpo_type === "Manual") {
		for (const row of form.items.filter((item) => item.item_code)) loadBuyingPrice(row)
	} else checkSelectedItemsForSupplier(supplier)
})
watch(() => form.lpo_type, () => {
	if (!hydrating.value && form.lpo_type !== "Manual" && form.supplier) checkSelectedItemsForSupplier(form.supplier)
})
watch(() => form.order_date, () => {
	if (!hydrating.value) form.items.filter((row) => row.item_code && !row.rate_edited).forEach((row) => loadBuyingPrice(row, { keepRateIfMissing: true }))
})
watch(() => form.tc_name, () => { if (!hydrating.value) applyTerms().catch(toastError) })

function addRow() {
	form.items.push({ item_code: "", item_name: "", controlled_item_type: "", controlled_procurement_catalog: 0, stock_uom: "", qty: 1, rate: 0, vat: "standard", notes: "", use_override: false, project: "", bill_no: "", boq_item: "", rate_edited: false, price_change_reason: "", price_loading: false, price_missing: false })
}

function normalizedAllocation(values) {
	return Object.fromEntries(allocationFields.map((field) => {
		const value = typeof values[field] === "string" ? values[field].trim() : values[field]
		return [field, value == null || emptyAllocationValues.has(String(value).toLowerCase()) ? "" : value]
	}))
}

const orderAllocationLabel = computed(() => {
	const { project, bill_no, boq_item } = normalizedAllocation(form)
	return project ? `${[project, bill_no, boq_item].filter(Boolean).join(" · ")} (from order)` : "Uses order allocation"
})

function toggleLineAllocation(row) {
	if (!row.use_override) Object.assign(row, normalizedAllocation(form))
	row.use_override = !row.use_override
}

function needsSubmitApproval(row) {
	return form.lpo_type !== "Manual" && ["Consumable", "Service"].includes(row.controlled_item_type) && row.item_code
		&& row.rate_edited && (row.fetched_rate == null || Number(row.rate) !== Number(row.fetched_rate) || Boolean(row.price_change_reason))
}

function purchaseOrderPayload() {
	return {
		...form,
		company: session.context.default_company || form.company,
		...normalizedAllocation(form),
		// without an override the line takes the order's allocation
		items: form.items.map((row) => ({ ...row, ...(row.use_override ? normalizedAllocation(row) : { project: "", bill_no: "", boq_item: "" }) })),
		terms: termsEditor.value?.innerHTML || form.terms,
	}
}

function creationRequestId() {
	const state = window.history.state || {}
	if (state.purchaseOrderRequestId) return state.purchaseOrderRequestId
	const id = window.crypto.randomUUID()
	window.history.replaceState({ ...state, purchaseOrderRequestId: id }, "")
	return id
}

async function save() {
	if (saving.value || createdOrderName.value) return
	const nonCatalog = form.items.filter((row) => row.item_code && row.not_in_catalog)
	if (nonCatalog.length) {
		toast(`Replace non-catalog items before saving: ${nonCatalog.map((row) => row.item_name || row.item_code).join(", ")}`, "error")
		return
	}
	saving.value = true
	try {
		const result = editing.value
			? await call("update_purchase_order", { name: props.name, data: purchaseOrderPayload() })
			: await call("create_purchase_order", { data: { ...purchaseOrderPayload(), creation_request_id: creationRequestId() } })
		if (!editing.value) createdOrderName.value = result.name
		priceApprovalStatus.value = result.price_approval_status || ""
		toast(`Purchase order ${result.name} ${result.price_approval_status?.startsWith("Pending") ? `is ${result.price_approval_status.toLowerCase()} price approval` : editing.value ? "updated" : "created as draft"}`)
		if (!editing.value) {
			await router.replace(`/purchase-orders/${result.name}/edit`)
			const { purchaseOrderRequestId, ...state } = window.history.state || {}
			window.history.replaceState(state, "")
		}
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

async function submitSavedOrder() {
	if (!editing.value || saving.value) return
	saving.value = true
	try {
		const result = await call("submit_document", { doctype: "Purchase Order", name: props.name })
		toast(result?.docstatus === 0 && result?.price_approval_status === "Pending CEO"
			? `Purchase order ${props.name} sent to CEO for price approval. It submits automatically once approved.`
			: `Purchase order ${props.name} submitted`)
		await router.replace(`/purchase-orders/${props.name}`)
	} catch (error) {
		toastError(error)
	} finally {
		saving.value = false
	}
}

addRow()

async function hydrateDuplicate(source) {
	try {
		const doc = await call("get_purchase_order_duplicate", { name: source })
		const manual = doc.custom_lpo_type === "Manual"
		hydrating.value = true
		Object.assign(form, {
			supplier: doc.supplier, lpo_type: doc.custom_lpo_type || "Standard", warehouse: doc.set_warehouse || "",
			contact_person: doc.contact_person || "", payment_terms_template: doc.payment_terms_template || "", tc_name: doc.tc_name || "", terms: doc.terms || "",
			taxes_and_charges: doc.taxes_and_charges || null, apply_discount_on: doc.apply_discount_on || "Net Total", additional_discount_percentage: doc.additional_discount_percentage || 0, discount_amount: doc.additional_discount_percentage ? 0 : doc.discount_amount || 0,
			project: doc.project || "", bill_no: doc.bill_no || "", boq_item: doc.boq_item || "",
			items: (doc.items || []).map((row) => ({ item_code: row.item_code, item_name: row.item_name, controlled_item_type: row.controlled_item_type || "",
				controlled_procurement_catalog: Number(row.controlled_procurement_catalog || 0), stock_uom: row.stock_uom,
				qty: row.qty, rate: row.rate, fetched_rate: manual ? row.rate : null, vat: row.vat, notes: row.description || "", rate_edited: manual, price_change_reason: "",
				price_loading: false, price_missing: false, not_in_catalog: !row.in_catalog,
				project: row.project || "", bill_no: row.bill_no || "", boq_item: row.boq_item || "",
				use_override: ["project", "bill_no", "boq_item"].some((field) => (row[field] || "") !== (doc[field] || "")),
			})),
		})
		if (!form.items.length) addRow()
		await nextTick()
		if (termsEditor.value) termsEditor.value.innerHTML = doc.terms || ""
		hydrating.value = false
		await loadContacts(doc.contact_person)
		if (!manual) form.items.filter((row) => row.item_code && !row.not_in_catalog).forEach((row) => loadBuyingPrice(row, { keepRateIfMissing: true }))
	} catch (error) {
		hydrating.value = false
		toastError(error)
	}
}

onMounted(async () => {
	if (!editing.value) {
		if (duplicateSource.value) await hydrateDuplicate(duplicateSource.value)
		return
	}
	try {
		const doc = await call("get_controlled_document", { doctype: "Purchase Order", name: props.name })
		if (doc.docstatus !== 0 || !doc.controlled_procurement || (doc.custom_lpo_type === "Manual" && ["Pending Accounts", "Pending CEO"].includes(doc.custom_po_price_status)) || ["Pending Accounts", "Pending CEO"].includes(doc.custom_lpo_approval_status)
			|| (doc.custom_lpo_approval_status === "Needs Correction" && doc.owner !== session.context.user && !session.context.can_override_lpo)) {
			toast("This Purchase Order cannot be edited as a draft")
			router.replace(`/purchase-orders/${props.name}`)
			return
		}
		hydrating.value = true
		Object.assign(form, {
			company: doc.company, supplier: doc.supplier, order_date: doc.transaction_date,
			required_by: doc.schedule_date, lpo_type: doc.custom_lpo_type || (doc.custom_is_provisional_po ? "Open" : "Standard"),
			warehouse: doc.set_warehouse || "",
			contact_person: doc.contact_person || "", payment_terms_template: doc.payment_terms_template || "", tc_name: doc.tc_name || "", terms: doc.terms || "",
			taxes_and_charges: doc.taxes_and_charges || null, apply_discount_on: doc.apply_discount_on || "Net Total", additional_discount_percentage: doc.additional_discount_percentage || 0, discount_amount: doc.additional_discount_percentage ? 0 : doc.discount_amount || 0, project: doc.project || "", bill_no: doc.bill_no || "", boq_item: doc.boq_item || "",
			items: (doc.items || []).map((row) => ({ docname: row.name, item_code: row.item_code, item_name: row.item_name, controlled_item_type: row.controlled_item_type,
				controlled_procurement_catalog: Number(row.controlled_procurement_catalog || 0), stock_uom: row.stock_uom,
				qty: row.qty, rate: row.rate, fetched_rate: row.rate, vat: row.vat, notes: row.description || "", rate_edited: true, price_change_reason: row.custom_price_change_reason || "",
				project: row.project || "", bill_no: row.bill_no || "", boq_item: row.boq_item || "",
				use_override: ["project", "bill_no", "boq_item"].some((field) => (row[field] || "") !== (doc[field] || "")),
			})),
		})
		priceApprovalStatus.value = doc.custom_po_price_status || ""
		if (!form.items.length) addRow()
		await nextTick()
		if (termsEditor.value) termsEditor.value.innerHTML = doc.terms || ""
		hydrating.value = false
		await loadContacts(doc.contact_person)
	} catch (error) {
		hydrating.value = false
		toastError(error)
	}
})
</script>

<template>
	<form @submit.prevent="save">
		<PageHeader :title="editing ? `Edit ${name}` : duplicateSource ? `Duplicate of ${duplicateSource}` : 'New Purchase Order'" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Purchase Orders', to: '/purchase-orders' }, { label: editing ? name : 'New' }]">
			<template #actions>
				<RouterLink :to="editing ? `/purchase-orders/${name}` : '/purchase-orders'" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving">{{ saving ? "Saving…" : editing ? "Save changes" : "Create order" }}</button>
				<button v-if="editing && form.lpo_type !== 'Manual' && !['Pending Accounts', 'Pending CEO'].includes(priceApprovalStatus)" type="button" class="cp-btn brand" :disabled="saving" @click="submitSavedOrder">Submit</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Order</h2>
			<div class="cp-grid-3">
				<label class="cp-field"><span>Order date<i>*</i></span><input v-model="form.order_date" type="date" class="cp-input" required /></label>
				<label class="cp-field"><span>LPO type</span><select v-model="form.lpo_type" class="cp-input"><option>Standard</option><option>Open</option><option v-if="editing || form.lpo_type === 'Manual'">Manual</option></select></label>
			</div>
			<p v-if="form.lpo_type === 'Manual'" class="cp-hint">Manual LPOs require Accounts approval, then CEO approval, before they are submitted.</p>
			<p v-if="form.lpo_type === 'Open'" class="cp-hint">Open LPO: the existing provisional purchase-order behavior applies automatically.</p>
			<div class="cp-grid-3">
				<div>
					<LinkSelect v-model="form.supplier" doctype="Supplier" label="Supplier" :required="true" />
					<label v-if="supplierChoiceItem && eligibleSuppliers.length > 1" class="cp-field" style="margin-top: 8px">
						<span>Suppliers linked to {{ form.items.find((row) => row.item_code === supplierChoiceItem)?.item_name || supplierChoiceItem }}</span>
						<select class="cp-input" :value="form.supplier" @change="form.supplier = $event.target.value">
							<option value="">Choose a supplier</option>
							<option v-for="supplier in eligibleSuppliers" :key="supplier.name" :value="supplier.name">{{ supplier.supplier_name || supplier.name }}</option>
						</select>
					</label>
					<small v-if="itemSupplierLoading" class="cp-hint">Finding suppliers linked to the item…</small>
					<small v-if="itemSupplierMessage" class="cp-overdue" role="alert">{{ itemSupplierMessage }}</small>
					<button type="button" class="cp-link sm" @click="supplierDialog = true">+ New supplier</button>
				</div>
				<label class="cp-field"><span>Company</span><input :value="form.company" class="cp-input" disabled title="Switch company from the top bar" /></label>
				<label class="cp-field"><span>Required by<i>*</i></span><input v-model="form.required_by" type="date" class="cp-input" required /></label>
			</div>
			<div class="cp-grid-3">
				<div>
					<LinkSelect v-model="form.payment_terms_template" doctype="Payment Terms Template" label="Payment terms" placeholder="Select payment terms" />
					<small class="cp-hint">Defaults from the supplier; change it here for this order.</small>
					<button v-if="form.supplier" type="button" class="cp-link sm" @click="editSupplierTerms = true">Edit supplier default</button>
				</div>
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
			<AllocationFields :boq-optional="session.context.boq_allocation_mode === 'project_only'" :model-value="{ project: form.project, bill_no: form.bill_no, boq_item: form.boq_item }" @update:model-value="Object.assign(form, $event)" />
			<p v-if="session.context.boq_allocation_mode === 'project_only'" class="cp-hint">For {{ session.context.default_company }}, Project is required; Bill No and BOQ Item are optional.</p>
		</section>

		<section class="cp-section">
			<div class="cp-section-bar">
				<h2 class="cp-section-title">Items</h2>
				<button type="button" class="cp-link" @click="addRow">+ Add item</button>
			</div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th style="width: 30%">Description</th><th style="width: 18%">Supplier</th><th class="num" style="width: 100px">Qty</th><th style="width: 60px">UOM</th><th class="num" style="width: 120px">Rate</th><th style="width: 104px">VAT</th><th class="num" style="width: 140px">Amount</th><th style="width: 40px" /></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="index">
							<tr>
								<td>
									<ItemPicker v-model="row.item_code" :display-name="row.item_name" :supplier="form.lpo_type === 'Manual' ? '' : form.supplier" :disabled="form.lpo_type === 'Manual' && !form.supplier" :hide-code="true" :unique-items="true" @selected="selectItem(row, $event)" @cleared="clearItem(row)" />
									<small v-if="row.item_code" class="cp-muted">{{ [row.item_code, row.controlled_item_type].filter(Boolean).join(" · ") }}</small>
									<span v-if="row.controlled_procurement_catalog" class="cp-pill info" style="margin-left: 6px">Controlled</span>
									<span v-if="needsSubmitApproval(row)" class="cp-pill warning" style="margin-left: 6px" title="Consumable/Service price differs from the catalog; this PO only">Needs CEO approval on submit</span>
									<span v-if="row.not_in_catalog" class="cp-pill warning" style="margin-left: 6px" title="Copied from a PO raised outside the catalog">Not in catalog: pick a catalog item</span>
									<small v-if="!row.use_override" class="cp-muted" style="display: block">{{ orderAllocationLabel }}</small>
									<button type="button" class="cp-link sm" @click="toggleLineAllocation(row)">{{ row.use_override ? "Use order allocation" : "Different project / BOQ for this line" }}</button>
								</td>
								<td>{{ row.item_code ? form.supplier : "—" }}</td>
								<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0.0001" step="any" required /></td>
								<td><span class="cp-muted">{{ row.stock_uom || "—" }}</span></td>
								<td><input v-model.number="row.rate" class="cp-input num" type="number" min="0.000001" step="any" :title="row.price_loading ? 'Loading buying price…' : ''" @input="row.rate_edited = true; row.price_missing = false" /><small v-if="row.price_loading" class="cp-hint">Loading price…</small><small v-else-if="row.price_missing" class="cp-overdue">No buying price; enter a rate</small><input v-if="row.rate_edited && (row.fetched_rate == null || Number(row.rate) !== Number(row.fetched_rate) || row.price_change_reason)" v-model="row.price_change_reason" class="cp-input" style="margin-top: 6px" placeholder="Reason for changed price" /></td>
								<td><VatSelect v-model="row.vat" /><small class="cp-line-vat">{{ formatCurrency(lineTax(index)) }}</small></td>
								<td class="num">{{ formatCurrency((row.qty || 0) * (row.rate || 0)) }}</td>
								<td><button type="button" class="cp-remove" :disabled="form.items.length === 1" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
							</tr>
							<tr v-if="row.use_override" class="cp-subrow">
								<td colspan="8"><AllocationFields :boq-optional="session.context.boq_allocation_mode === 'project_only'" :model-value="row" @update:model-value="Object.assign(row, $event)" /></td>
							</tr>
							<tr class="cp-subrow"><td colspan="8"><label class="cp-field"><span>Line description</span><input v-model="row.notes" class="cp-input" placeholder="Optional description for this purchase-order line" /></label></td></tr>
						</template>
					</tbody>
					<tfoot><tr><td colspan="6" class="num">Net total</td><td class="num"><strong>{{ formatCurrency(total) }}</strong></td><td /></tr></tfoot>
				</table>
			</div>
			<p class="cp-hint">Choose a supplier first to see its items, or choose an item first to find its linked suppliers. Only approved catalog items can be ordered.</p>
			<TaxSection v-model="form.taxes_and_charges" :templates="taxTemplates" :totals="totals" :loading="taxLoading" :subtotal="total" :discount-percentage="Number(form.additional_discount_percentage) || 0" />
			<div class="cp-grid-3" style="margin-top: 16px">
				<label class="cp-field"><span>Order discount %</span><input v-model.number="form.additional_discount_percentage" class="cp-input" type="number" min="0" max="100" step="any" @input="form.discount_amount = 0" /></label>
				<label class="cp-field"><span>Order discount amount</span><input v-model.number="form.discount_amount" class="cp-input" type="number" min="0" step="any" @input="form.additional_discount_percentage = 0" /></label>
				<label class="cp-field"><span>Discount applied on</span><select v-model="form.apply_discount_on" class="cp-input"><option>Net Total</option><option>Grand Total</option></select></label>
			</div>
			<p v-if="priceApprovalStatus === 'Pending CEO'" class="cp-hint">Saving another change replaces the pending price proposal with a new CEO decision for this latest draft.</p>
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
		<SupplierDialog v-if="supplierDialog" @close="supplierDialog = false" @saved="onSupplierSaved" />
		<SupplierDialog v-if="editSupplierTerms" :supplier="form.supplier" @close="editSupplierTerms = false" @saved="onSupplierSaved" />
	</form>
</template>
