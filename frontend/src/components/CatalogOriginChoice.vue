<script setup>
defineProps({ canChoose: Boolean, modelValue: Boolean })
defineEmits(["update:modelValue"])
</script>

<template>
	<label v-if="canChoose" class="cp-field">
		<span>Request as</span>
		<select class="cp-input" :value="modelValue ? 'Accounts' : 'Purchase'" @change="$emit('update:modelValue', $event.target.value === 'Accounts')">
			<option value="Purchase">Purchase — Accounts Manager, then CEO</option>
			<option value="Accounts">Accounts — CEO approval</option>
		</select>
		<small class="cp-hint">Purchase is the default when you hold both roles. Your selection is saved with the request.</small>
	</label>
</template>
