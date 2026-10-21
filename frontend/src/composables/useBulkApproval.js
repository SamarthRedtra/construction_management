import { computed, reactive, ref } from "vue"
import { call } from "@/api"
import { toast, toastError } from "@/toast"

/**
 * Multi-select + bulk approve/reject for procurement queues.
 * Returns a reactive object so template access unwraps nested refs
 * (plain `{ busy: ref() }` stays truthy in v-if and sticks the overlay open).
 *
 * @param {(row: object) => boolean} canSelect
 * @param {(row: object) => string} rowKey
 */
export function useBulkApproval(canSelect, rowKey = (row) => row.name) {
	const selected = ref(new Set())
	const busy = ref(false)
	const progress = ref({ current: 0, total: 0, label: "" })

	const selectedCount = computed(() => selected.value.size)
	const hasSelection = computed(() => selected.value.size > 0)

	function isSelected(row) {
		return selected.value.has(rowKey(row))
	}

	function toggle(row, checked) {
		if (!canSelect(row)) return
		const next = new Set(selected.value)
		const key = rowKey(row)
		if (checked) next.add(key)
		else next.delete(key)
		selected.value = next
	}

	function clearSelection() {
		selected.value = new Set()
	}

	function selectAllEligible(rows) {
		const next = new Set()
		for (const row of rows || []) {
			if (canSelect(row)) next.add(rowKey(row))
		}
		selected.value = next
	}

	function allEligibleSelected(rows) {
		const eligible = (rows || []).filter(canSelect)
		return eligible.length > 0 && eligible.every((row) => selected.value.has(rowKey(row)))
	}

	function toggleSelectAll(rows, checked) {
		if (checked) selectAllEligible(rows)
		else clearSelection()
	}

	/**
	 * Call a server bulk method with selected rows.
	 * @param {object[]} rows
	 * @param {string} method
	 * @param {object} extraArgs
	 * @param {{ mapRow?: (row: object) => object, useRows?: boolean, actionLabel?: string }} [options]
	 */
	async function runBulk(rows, method, extraArgs = {}, options = {}) {
		const { mapRow = null, useRows = false, actionLabel = "Processing" } = options
		const keys = selected.value
		const chosen = (rows || []).filter((row) => keys.has(rowKey(row)) && canSelect(row))
		if (!chosen.length) {
			toastError(new Error("Select at least one eligible request."))
			return null
		}
		busy.value = true
		progress.value = { current: 0, total: chosen.length, label: actionLabel }
		try {
			const payload = { ...extraArgs }
			if (useRows) payload.rows = chosen.map(mapRow || ((row) => ({ name: rowKey(row) })))
			else payload.names = chosen.map((row) => rowKey(row))

			const summary = await call(method, payload)
			const approved = summary?.approved ?? 0
			const failed = summary?.failed ?? 0
			if (failed && approved) toast(`${actionLabel}: ${approved} succeeded, ${failed} failed`)
			else if (failed) toastError(new Error(formatFailures(summary)))
			else toast(`${actionLabel}: ${approved} succeeded`)
			clearSelection()
			return summary
		} catch (error) {
			toastError(error)
			return null
		} finally {
			busy.value = false
			progress.value = { current: 0, total: 0, label: "" }
		}
	}

	return reactive({
		selected,
		selectedCount,
		hasSelection,
		busy,
		progress,
		isSelected,
		toggle,
		clearSelection,
		selectAllEligible,
		allEligibleSelected,
		toggleSelectAll,
		runBulk,
	})
}

function formatFailures(summary) {
	const errors = (summary?.results || []).filter((r) => !r.ok).slice(0, 3)
	if (!errors.length) return "Bulk action failed"
	return errors.map((r) => `${r.name}: ${r.error || "failed"}`).join("\n")
}
