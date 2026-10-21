<script setup>
import { computed } from "vue"

const props = defineProps({
	/** @type {{ key: string, label: string, options: { value: string, label: string }[] }[]} */
	groups: { type: Array, required: true },
	modelValue: { type: Object, default: () => ({}) },
})

const emit = defineEmits(["update:modelValue"])

const activeCount = computed(() =>
	Object.values(props.modelValue || {}).filter((value) => value !== "" && value != null).length
)

function isActive(groupKey, value) {
	return (props.modelValue?.[groupKey] || "") === value
}

function select(groupKey, value) {
	const next = { ...props.modelValue }
	next[groupKey] = isActive(groupKey, value) ? "" : value
	emit("update:modelValue", next)
}

function clear() {
	const next = {}
	for (const group of props.groups) next[group.key] = ""
	emit("update:modelValue", next)
}
</script>

<template>
	<div class="cp-approval-filters">
		<div v-for="group in groups" :key="group.key" class="cp-chip-group">
			<span class="cp-chip-group-label">{{ group.label }}</span>
			<div class="cp-chips">
				<button
					v-for="option in group.options"
					:key="option.value"
					type="button"
					class="cp-chip"
					:class="{ active: isActive(group.key, option.value) }"
					@click="select(group.key, option.value)"
				>
					{{ option.label }}
				</button>
			</div>
		</div>
		<button v-if="activeCount" type="button" class="cp-btn sm cp-clear-filters" @click="clear">Clear filters</button>
	</div>
</template>
