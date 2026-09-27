import { ref, watch } from "vue"
import { call } from "@/api"
import { debounce, session } from "@/utils"

export const VAT_CHOICES = [
	{ value: "standard", label: "5%" },
	{ value: "zero", label: "Zero" },
	{ value: "exempt", label: "Exempt" },
]

const optionsByCompany = {}

async function loadOptions(company) {
	if (!optionsByCompany[company]) optionsByCompany[company] = call("get_tax_options", { company })
	return optionsByCompany[company]
}

// Keeps a form's tax template defaulted and its totals in step with ERPNext's own calculation.
// `form` needs `taxes_and_charges` and `items` ({ item_code, qty, rate, vat }); pass `lines` to
// preview a derived list instead (e.g. only rows with a qty to receive).
export function useTaxes(doctype, form, { lines = () => form.items, defaultTemplate = true } = {}) {
	const templates = ref([])
	const totals = ref(null)
	const loading = ref(false)

	loadOptions(session.context.default_company).then((options) => {
		templates.value = options.templates
		// null = not chosen yet; "" = the user picked "No tax"
		if (defaultTemplate && form.taxes_and_charges == null) form.taxes_and_charges = options.default_template || ""
	})

	const refresh = debounce(async () => {
		const items = lines().map((row) => ({ item_code: row.item_code, qty: row.qty, rate: row.rate, vat: row.vat || "standard" }))
		if (!items.some((row) => row.item_code)) {
			totals.value = null
			return
		}
		loading.value = true
		try {
			totals.value = await call("preview_totals", {
				doctype,
				data: { company: session.context.default_company, supplier: form.supplier, taxes_and_charges: form.taxes_and_charges, items },
			})
		} catch {
			totals.value = null
		} finally {
			loading.value = false
		}
	}, 350)

	watch(() => [form.taxes_and_charges, lines().map((row) => [row.item_code, row.qty, row.rate, row.vat])], refresh, { deep: true, immediate: true })

	// VAT on one line, as returned by the last preview (same order as `lines()`)
	function lineTax(index) {
		return totals.value?.line_tax?.[index] ?? 0
	}

	return { templates, totals, loading, lineTax }
}
