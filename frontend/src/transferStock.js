import { computed, onUnmounted, ref, watch } from "vue"
import { call } from "@/api"

export function useTransferStock(warehouse, items) {
	const balances = ref({})
	const loading = ref(false)
	const error = ref("")
	const requested = computed(() => {
		const totals = {}
		for (const row of items.value || []) {
			if (row.item_code) totals[row.item_code] = (totals[row.item_code] || 0) + (Number(row.qty) || 0)
		}
		return totals
	})
	let requestId = 0
	let timer

	async function refresh() {
		const currentRequest = ++requestId
		const source = warehouse.value
		const codes = Object.keys(requested.value)
		balances.value = {}
		error.value = ""
		if (!source || !codes.length) {
			loading.value = false
			return
		}
		loading.value = true
		try {
			const result = await call("get_transfer_stock_preview", { source_warehouse: source, item_codes: codes })
			if (currentRequest === requestId) balances.value = result.balances || {}
		} catch (requestError) {
			if (currentRequest === requestId) error.value = requestError.message || "Could not check stock"
		} finally {
			if (currentRequest === requestId) loading.value = false
		}
	}

	function state(itemCode) {
		if (!itemCode || !warehouse.value) return "unknown"
		if (loading.value) return "loading"
		if (error.value) return "error"
		if (!Object.hasOwn(balances.value, itemCode)) return "unknown"
		return requested.value[itemCode] > balances.value[itemCode] + 0.0001 ? "short" : "enough"
	}

	function shortage(itemCode) {
		return Math.max((requested.value[itemCode] || 0) - (balances.value[itemCode] || 0), 0)
	}

	watch([warehouse, () => Object.keys(requested.value).sort().join("\u0000")], () => {
		clearTimeout(timer)
		timer = setTimeout(refresh, 180)
	}, { immediate: true })
	onUnmounted(() => clearTimeout(timer))

	return { balances, loading, error, requested, refresh, state, shortage }
}
