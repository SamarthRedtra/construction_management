<script setup>
import LinkSelect from "@/components/LinkSelect.vue"

defineProps({
	row: { type: Object, required: true },
	company: { type: String, required: true },
	allowUomEdit: { type: Boolean, default: false },
})
</script>

<template>
	<section class="cp-correction-row">
		<h3>{{ row.action }} · {{ row.item_code || row.result_item || row.item_name }}</h3>
		<div class="cp-grid-2">
			<label class="cp-field"><span>Item Code (permanent)</span><input :value="row.item_code || row.result_item || 'Assigned on approval'" class="cp-input" disabled /></label>
			<template v-if="row.action === 'Change Item Group'">
				<LinkSelect v-model="row.item_group" doctype="Item Group" label="Item Group" :required="true" :filters="{ is_group: 0 }" />
			</template>
			<template v-else-if="row.action === 'Link Supplier'">
				<LinkSelect v-model="row.supplier" doctype="Supplier" label="Supplier" :required="true" :filters="{ disabled: 0 }" />
			</template>
			<template v-else>
				<label class="cp-field"><span>Item Name / Description<i>*</i></span><input v-model="row.item_name" class="cp-input" required /></label>
				<LinkSelect v-model="row.item_group" doctype="Item Group" label="Item Group" :required="true" :filters="{ is_group: 0 }" />
				<label class="cp-field"><span>Item Type<i>*</i></span><select v-model="row.item_type" class="cp-input" required><option>Stockable</option><option>Consumable</option><option>Asset</option><option>Service</option></select></label>
				<LinkSelect v-model="row.stock_uom" doctype="UOM" label="Stock UOM" :required="true" :disabled="!allowUomEdit && row.action !== 'Create'" />
				<LinkSelect v-model="row.supplier" doctype="Supplier" label="Supplier" :required="true" :filters="{ disabled: 0 }" />
				<label class="cp-field"><span>Buying Rate</span><input v-model.number="row.rate" type="number" min="0" step="any" class="cp-input" /><small class="cp-hint">Zero means no buying-price change.</small></label>
				<LinkSelect v-if="row.item_type === 'Asset'" v-model="row.asset_category" doctype="Asset Category" label="Asset Category" />
				<LinkSelect v-if="row.item_type === 'Service'" v-model="row.expense_account" doctype="Account" label="Service Expense Account" :filters="{ company, is_group: 0 }" />
			</template>
		</div>
	</section>
</template>

<style scoped>
.cp-correction-row { border-top: 1px solid var(--border); padding-top: 16px; }
.cp-correction-row h3 { margin: 0 0 14px; font-size: 15px; }
</style>
