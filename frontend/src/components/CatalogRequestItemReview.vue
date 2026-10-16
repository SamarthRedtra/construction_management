<script setup>
const props = defineProps({
	row: { type: Object, required: true },
	current: { type: Object, default: null },
	currency: { type: String, default: "" },
	initiallyOpen: { type: Boolean, default: false },
})

function display(value) {
	if (Array.isArray(value)) return value.join(", ") || "—"
	return value === 0 || value ? String(value) : "—"
}

function money(value) {
	if (value === null || value === undefined || value === "") return "No current rate"
	return `${props.currency ? `${props.currency} ` : ""}${Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 })}`
}

function proposedRate() {
	if (["Disable", "Change Item Group", "Link Supplier"].includes(props.row.action) || Number(props.row.rate) <= 0) {
		return props.row.action === "Create" ? "No buying price proposed" : "No buying-price change"
	}
	return money(props.row.rate)
}

function proposed(field) {
	if (props.row.action === "Change Item Group" && field !== "item_group") return display(props.current?.[field])
	if (props.row.action === "Link Supplier" && field !== "supplier") return display(props.current?.[field])
	if (props.row.action === "Disable") return display(props.current?.[field])
	return display(props.row[field])
}
</script>

<template>
	<details class="cp-review-item" :open="initiallyOpen">
		<summary><strong>{{ row.item_name }}</strong><span>{{ row.item_code || row.result_item || 'New Item Code on approval' }} · {{ row.action }}</span></summary>
		<p v-if="row.action !== 'Create' && !current" class="cp-hint">The current Item could not be found. Approval will be checked against the live Item.</p>
		<table class="cp-table"><thead><tr><th>Field</th><th>Current</th><th>Proposed</th></tr></thead><tbody>
			<tr><th>Item Name / Description</th><td>{{ display(current?.item_name) }}</td><td>{{ proposed('item_name') }}</td></tr>
			<tr><th>Item Group</th><td>{{ display(current?.item_group) }}</td><td>{{ proposed('item_group') }}</td></tr>
			<tr><th>Item Type</th><td>{{ display(current?.item_type) }}</td><td>{{ proposed('item_type') }}</td></tr>
			<tr><th>Stock UOM</th><td>{{ display(current?.stock_uom) }}</td><td>{{ proposed('stock_uom') }}</td></tr>
			<tr><th>Supplier(s)</th><td>{{ display(current?.suppliers) }}</td><td>{{ row.action === 'Change Item Group' || row.action === 'Disable' ? 'No change' : display(row.supplier) }}</td></tr>
			<tr><th>Buying Rate (Standard Buying)</th><td>{{ current ? money(current.rate) : 'New item' }}</td><td>{{ proposedRate() }}</td></tr>
			<tr v-if="row.item_type === 'Asset' || current?.asset_category"><th>Asset Category</th><td>{{ display(current?.asset_category) }}</td><td>{{ proposed('asset_category') }}</td></tr>
			<tr v-if="row.item_type === 'Service' || current?.expense_account"><th>Service Expense Account</th><td>{{ display(current?.expense_account) }}</td><td>{{ proposed('expense_account') }}</td></tr>
			<tr v-if="row.action === 'Disable'"><th>Availability</th><td>Enabled</td><td>Disabled after CEO approval</td></tr>
		</tbody></table>
	</details>
</template>

<style scoped>
.cp-review-item { border: 1px solid var(--border); border-radius: 9px; margin: 12px 0; overflow: hidden; }
.cp-review-item summary { cursor: pointer; display: flex; justify-content: space-between; gap: 12px; padding: 12px; }
.cp-review-item summary span { color: var(--muted); font-size: 12px; }
.cp-review-item .cp-table { margin: 0; }
</style>
