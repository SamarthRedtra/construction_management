<script setup>
import { ref, watch } from "vue"
import { linkSearch } from "@/api"
import { debounce } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	doctype: { type: String, required: true },
	label: { type: String, default: "" },
	placeholder: { type: String, default: "" },
	required: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
	filters: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:modelValue", "selected"])
const query = ref(props.modelValue || "")
const options = ref([])
const open = ref(false)
const highlighted = ref(0)
const anchor = ref(null)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)

const search = debounce(async () => {
	try {
		options.value = await linkSearch(props.doctype, query.value, props.filters)
		highlighted.value = 0
		place()
	} catch {
		options.value = []
	}
}, 200)

function onFocus() {
	open.value = true
	search()
}

function onInput() {
	open.value = true
	if (!query.value) emit("update:modelValue", "")
	search()
}

function select(option) {
	query.value = option.value
	open.value = false
	emit("update:modelValue", option.value)
	emit("selected", option)
}

function onBlur() {
	// allow a click on an option to land before closing
	setTimeout(() => {
		open.value = false
		if (query.value !== props.modelValue) query.value = props.modelValue || ""
	}, 150)
}

function onKey(event) {
	if (!open.value || !options.value.length) return
	if (event.key === "ArrowDown") highlighted.value = Math.min(highlighted.value + 1, options.value.length - 1)
	else if (event.key === "ArrowUp") highlighted.value = Math.max(highlighted.value - 1, 0)
	else if (event.key === "Enter") select(options.value[highlighted.value])
	else return
	event.preventDefault()
}

watch(() => props.modelValue, (value) => { query.value = value || "" })
</script>

<template>
	<label class="cp-field">
		<span v-if="label">{{ label }}<i v-if="required">*</i></span>
		<div ref="anchor" class="cp-combo">
			<input
				v-model="query"
				class="cp-input"
				:placeholder="placeholder || `Select ${label || doctype}`"
				:required="required"
				:disabled="disabled"
				autocomplete="off"
				@focus="onFocus"
				@input="onInput"
				@blur="onBlur"
				@keydown="onKey"
			/>
			<svg viewBox="0 0 24 24" class="cp-combo-caret"><path d="m7 10 5 5 5-5" /></svg>
			<Teleport to="body">
			<div v-if="open && options.length" class="cp-options cp-floating" :style="panelStyle">
				<button
					v-for="(option, index) in options"
					:key="option.value"
					type="button"
					:class="{ highlighted: index === highlighted }"
					@mousedown.prevent="select(option)"
				>
					<strong>{{ option.label || option.value }}</strong>
					<small v-if="option.description">{{ option.description }}</small>
				</button>
			</div>
			</Teleport>
		</div>
	</label>
</template>
