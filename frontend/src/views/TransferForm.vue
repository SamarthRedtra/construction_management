<script setup>
import { reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "@/api"
import { toast, toastError } from "@/toast"
import { session, today, companyFilters } from "@/utils"
import AllocationFields from "@/components/AllocationFields.vue"
import ItemPicker from "@/components/ItemPicker.vue"
import LinkSelect from "@/components/LinkSelect.vue"
import PageHeader from "@/components/PageHeader.vue"

const router = useRouter()
const form = reactive({ company: session.context.default_company || "", posting_date: today(), source_warehouse: "", target_warehouse: "", project: "", bill_no: "", boq_item: "", items: [] })
const saving = ref(false)

function addRow() {
	form.items.push({ item_code: "", qty: 1, rate: 0, source_warehouse: "", target_warehouse: "", use_override: false, project: "", bill_no: "", boq_item: "" })
}

async function save() {
	saving.value = true
	try {
		const items = form.items.map((row) => ({
			...row,
			source_warehouse: row.source_warehouse || form.source_warehouse,
			target_warehouse: row.target_warehouse || form.target_warehouse,
		}))
		const result = await call("create_material_transfer", { data: { ...form, items } })
		toast(`Material transfer ${result.name} created as draft`)
		router.push(`/transfers/${result.name}`)
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
		<PageHeader title="New Material Transfer" :breadcrumbs="[{ label: 'Procurement', to: '/dashboard' }, { label: 'Material Transfers', to: '/transfers' }, { label: 'New' }]">
			<template #actions>
				<RouterLink to="/transfers" class="cp-btn">Cancel</RouterLink>
				<button type="submit" class="cp-btn primary" :disabled="saving">{{ saving ? "Creating…" : "Create transfer" }}</button>
			</template>
		</PageHeader>

		<section class="cp-section">
			<h2 class="cp-section-title">Transfer</h2>
			<div class="cp-grid-3">
				<LinkSelect v-model="form.source_warehouse" doctype="Warehouse" label="From warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
				<LinkSelect v-model="form.target_warehouse" doctype="Warehouse" label="To warehouse" :required="true" :filters="companyFilters({ is_group: 0 })" />
				<label class="cp-field"><span>Posting date<i>*</i></span><input v-model="form.posting_date" class="cp-input" type="date" required /></label>
			</div>
			<AllocationFields :model-value="{ project: form.project, bill_no: form.bill_no, boq_item: form.boq_item }" @update:model-value="Object.assign(form, $event)" />
		</section>

		<section class="cp-section">
			<div class="cp-section-bar">
				<h2 class="cp-section-title">Stockable items</h2>
				<button type="button" class="cp-link" @click="addRow">+ Add item</button>
			</div>
			<div class="cp-card">
				<table class="cp-table cp-edit-table">
					<thead><tr><th style="width: 36%">Description</th><th class="num" style="width: 100px">Qty</th><th>From override</th><th>To override</th><th style="width: 40px" /></tr></thead>
					<tbody>
						<template v-for="(row, index) in form.items" :key="index">
							<tr>
								<td>
									<ItemPicker v-model="row.item_code" :stockable-only="true" />
									<button type="button" class="cp-link sm" @click="row.use_override = !row.use_override">{{ row.use_override ? "Use transfer allocation" : "Different project / BOQ for this line" }}</button>
								</td>
								<td><input v-model.number="row.qty" class="cp-input num" type="number" min="0.0001" step="any" required /></td>
								<td><LinkSelect v-model="row.source_warehouse" doctype="Warehouse" :placeholder="form.source_warehouse || 'Same as transfer'" :filters="companyFilters({ is_group: 0 })" /></td>
								<td><LinkSelect v-model="row.target_warehouse" doctype="Warehouse" :placeholder="form.target_warehouse || 'Same as transfer'" :filters="companyFilters({ is_group: 0 })" /></td>
								<td><button type="button" class="cp-remove" :disabled="form.items.length === 1" aria-label="Remove line" @click="form.items.splice(index, 1)">×</button></td>
							</tr>
							<tr v-if="row.use_override" class="cp-subrow">
								<td colspan="5"><AllocationFields :model-value="row" @update:model-value="Object.assign(row, $event)" /></td>
							</tr>
						</template>
					</tbody>
				</table>
			</div>
			<p class="cp-hint">Only controlled Stockable items can be transferred.</p>
		</section>
	</form>
</template>
