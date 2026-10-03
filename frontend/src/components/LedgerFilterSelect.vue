<script setup>
import { ref, watch } from "vue"
import { request } from "@/api"
import { toastError } from "@/toast"
import { debounce } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	field: { type: String, required: true },
	label: { type: String, required: true },
	receipt: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue"])
const query = ref(props.modelValue)
const options = ref([])
const open = ref(false)
const loading = ref(false)
const anchor = ref(null)
const highlighted = ref(0)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)
let searchId = 0

const search = debounce(async (id, term) => {
	try {
		const rows = await request("construction_management.api.procurement_insights.get_stock_ledger_options",
			{ field: props.field, search: term, receipt: props.receipt }, "GET")
		if (id !== searchId || !open.value) return
		options.value = rows || []
		highlighted.value = 0
		place()
	} catch (error) {
		if (id === searchId) { options.value = []; toastError(error) }
	} finally {
		if (id === searchId) loading.value = false
	}
}, 200)

function queueSearch() {
	const id = ++searchId
	loading.value = true
	options.value = []
	search(id, query.value)
}

function onFocus() {
	open.value = true
	queueSearch()
}

function onInput() {
	open.value = true
	emit("update:modelValue", "")
	queueSearch()
}

function select(option) {
	query.value = option.value
	open.value = false
	emit("update:modelValue", option.value)
}

function onBlur() {
	setTimeout(() => { open.value = false; query.value = props.modelValue || "" }, 150)
}

function onKey(event) {
	if (!open.value || !options.value.length) return
	if (event.key === "ArrowDown") highlighted.value = Math.min(highlighted.value + 1, options.value.length - 1)
	else if (event.key === "ArrowUp") highlighted.value = Math.max(highlighted.value - 1, 0)
	else if (event.key === "Enter") select(options.value[highlighted.value])
	else return
	event.preventDefault()
}

watch(() => props.modelValue, (value) => {
	if (value || !open.value) query.value = value || ""
})
</script>

<template>
	<label class="cp-field">
		<span>{{ label }}</span>
		<div ref="anchor" class="cp-combo">
			<input v-model="query" class="cp-input" :placeholder="`Search ${label.toLowerCase()}…`" autocomplete="off"
				@focus="onFocus" @input="onInput" @blur="onBlur" @keydown="onKey" />
			<svg viewBox="0 0 24 24" class="cp-combo-caret"><path d="m7 10 5 5 5-5" /></svg>
			<Teleport to="body">
				<div v-if="open" class="cp-options cp-floating" :style="panelStyle">
					<button v-for="(option, index) in options" :key="option.value" type="button"
						:class="{ highlighted: index === highlighted }" @mousedown.prevent="select(option)">
						<strong>{{ option.label || option.value }}</strong>
						<small v-if="option.label && option.label !== option.value">{{ option.value }}</small>
					</button>
					<span v-if="!loading && !options.length" class="cp-hint">No matching {{ label.toLowerCase() }} values</span>
					<span v-else-if="loading" class="cp-hint">Searching…</span>
				</div>
			</Teleport>
		</div>
	</label>
</template>
