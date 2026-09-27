<script setup>
import { formatCurrency } from "@/utils"

// Tax template picker + ERPNext-calculated totals, shown under a form's items table.
defineProps({
	modelValue: { type: String, default: "" },
	templates: { type: Array, default: () => [] },
	totals: { type: Object, default: null },
	loading: { type: Boolean, default: false },
	subtotal: { type: Number, default: 0 },
})
defineEmits(["update:modelValue"])
</script>

<template>
	<div class="cp-tax-section">
		<label class="cp-field cp-tax-template">
			<span>Tax template</span>
			<select class="cp-input" :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
				<option value="">No tax</option>
				<option v-for="template in templates" :key="template" :value="template">{{ template }}</option>
			</select>
			<small class="cp-hint">Applies to every line; switch a line to Zero or Exempt in its VAT column.</small>
		</label>
		<dl class="cp-totals cp-card" :class="{ 'is-loading': loading }">
			<div><dt>Net total</dt><dd>{{ formatCurrency(totals ? totals.net_total : subtotal) }}</dd></div>
			<div v-for="tax in totals?.taxes || []" :key="tax.description"><dt>{{ tax.description }}<template v-if="tax.rate"> ({{ tax.rate }}%)</template></dt><dd>{{ formatCurrency(tax.amount) }}</dd></div>
			<div class="grand"><dt>Grand total</dt><dd>{{ formatCurrency(totals ? totals.grand_total : subtotal) }}</dd></div>
		</dl>
	</div>
</template>
