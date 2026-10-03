<script setup>
import { ref, watch } from "vue"
import { call } from "@/api"

const props = defineProps({
	itemCode: { type: String, required: true },
	supplier: { type: String, default: "" },
	priceList: { type: String, default: "Standard Buying" },
	company: { type: String, default: "" },
})
const history = ref(null)
const loading = ref(false)
const error = ref("")
let loadId = 0

async function load(more = false) {
	if (!props.itemCode || !props.priceList) return
	const id = ++loadId
	loading.value = true
	error.value = ""
	try {
		const result = await call("get_price_history", {
			item_code: props.itemCode, supplier: props.supplier, price_list: props.priceList,
			company: props.company, start: more ? history.value?.rows.length || 0 : 0,
		})
		if (id !== loadId) return
		history.value = more ? { ...result, rows: [...history.value.rows, ...result.rows] } : result
	} catch (cause) {
		if (id === loadId) error.value = cause.message || "Could not load price history"
	} finally {
		if (id === loadId) loading.value = false
	}
}

watch(() => [props.itemCode, props.supplier, props.priceList, props.company], () => load(), { immediate: true })
</script>

<template>
	<section class="cp-stack">
		<h3 class="cp-section-title">Applied price history · {{ itemCode }} · {{ supplier || "General" }}</h3>
		<p v-if="loading && !history" class="cp-muted">Loading price history…</p>
		<p v-if="error" class="cp-overdue">{{ error }}</p>
		<template v-if="history">
			<p>Current {{ supplier ? "supplier-specific" : "general" }} price:
				<strong>{{ history.current ? `${history.currency} ${history.current.rate}` : "Not set" }}</strong>
				<small v-if="history.current"> · {{ history.current.item_price }}</small>
			</p>
			<p v-if="history.general" class="cp-muted">General buying price: {{ history.currency }} {{ history.general.rate }} · {{ history.general.item_price }}. It is a fallback only when no supplier-specific price exists.</p>
			<p v-if="history.catalog_origin" class="cp-muted">Verified catalog approval: {{ history.currency }} {{ history.catalog_origin.rate }} · {{ history.catalog_origin.request }} · {{ history.catalog_origin.company }}<span v-if="history.catalog_origin.approved_by"> · {{ history.catalog_origin.approved_by }} on {{ history.catalog_origin.approved_on }}</span>. Earlier catalog changes without a verifiable rate are not shown.</p>
			<div v-if="history.rows.length" style="overflow-x: auto">
				<table class="cp-table"><thead><tr><th>Applied on</th><th>Old → new</th><th>Source</th><th>Approved by</th></tr></thead>
					<tbody><tr v-for="row in history.rows" :key="row.name">
						<td>{{ row.decided_on }}<small>{{ row.company }}</small></td>
						<td>{{ row.old_rate == null ? (supplier ? "New supplier price" : "New general price") : `${history.currency} ${row.old_rate}` }}<small v-if="row.general_fallback_rate != null">General fallback at approval: {{ history.currency }} {{ row.general_fallback_rate }}</small> → <strong>{{ history.currency }} {{ row.proposed_rate }}</strong><small>{{ row.reason }}</small></td>
						<td>{{ row.source }}<small>{{ row.purchase_order || row.name }}</small></td>
						<td>{{ row.decided_by }}</td>
					</tr></tbody>
				</table>
			</div>
			<p v-else class="cp-muted">No verified applied price changes are recorded for this item, supplier and price list. Legacy prices may predate approval tracking.</p>
			<button v-if="history.has_more" class="cp-btn sm" :disabled="loading" @click="load(true)">{{ loading ? "Loading…" : "Load more history" }}</button>
		</template>
	</section>
</template>
