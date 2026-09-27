<script setup>
import { VAT_CHOICES } from "@/taxes"

defineProps({ modelValue: { type: String, default: "standard" }, disabled: { type: Boolean, default: false } })
defineEmits(["update:modelValue"])
</script>

<template>
	<select class="cp-input cp-vat-select" :value="modelValue || 'standard'" :disabled="disabled" aria-label="VAT" @change="$emit('update:modelValue', $event.target.value)">
		<option v-for="choice in VAT_CHOICES" :key="choice.value" :value="choice.value">{{ choice.label }}</option>
	</select>
</template>
