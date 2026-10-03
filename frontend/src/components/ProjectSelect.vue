<script setup>
import { ref, watch } from "vue"
import { call } from "@/api"
import { debounce, session } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	required: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const query = ref(props.modelValue)
const selectedLabel = ref(props.modelValue)
const options = ref([])
const open = ref(false)
const highlighted = ref(0)
const anchor = ref(null)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)
let labelRevision = 0
let searchRevision = 0

function projectLabel(row) {
	return row.project_name && row.project_name !== row.name ? `${row.name} — ${row.project_name}` : row.name
}

const search = debounce(async () => {
	const revision = ++searchRevision
	const text = query.value
	const term = props.modelValue && text === selectedLabel.value ? "" : text
	try {
		const rows = await call("get_procurement_projects", { search: term, company: session.context.default_company })
		if (revision !== searchRevision || text !== query.value || !open.value) return
		options.value = rows
		highlighted.value = 0
		place()
	} catch {
		if (revision === searchRevision) options.value = []
	}
}, 200)

function onInput() {
	if (props.modelValue) emit("update:modelValue", "")
	open.value = true
	search()
}

function select(row) {
	selectedLabel.value = projectLabel(row)
	query.value = selectedLabel.value
	open.value = false
	emit("update:modelValue", row.name)
}

function onKey(event) {
	if (!open.value || !options.value.length) return
	if (event.key === "ArrowDown") highlighted.value = Math.min(highlighted.value + 1, options.value.length - 1)
	else if (event.key === "ArrowUp") highlighted.value = Math.max(highlighted.value - 1, 0)
	else if (event.key === "Enter") select(options.value[highlighted.value])
	else return
	event.preventDefault()
}

function onBlur() {
	setTimeout(() => {
		open.value = false
		query.value = selectedLabel.value || ""
	}, 150)
}

watch(() => props.modelValue, async (name) => {
	const revision = ++labelRevision
	if (!name) {
		selectedLabel.value = ""
		if (!open.value) query.value = ""
		return
	}
	try {
		const rows = await call("get_procurement_projects", { selected: name, company: session.context.default_company })
		if (revision !== labelRevision || name !== props.modelValue) return
		selectedLabel.value = rows.length ? projectLabel(rows[0]) : name
		query.value = selectedLabel.value
	} catch {
		if (revision === labelRevision) query.value = name
	}
}, { immediate: true })
</script>

<template>
	<label class="cp-field">
		<span>Project<i v-if="required">*</i></span>
		<div ref="anchor" class="cp-combo">
			<input v-model="query" class="cp-input" placeholder="Search project number or name" autocomplete="off"
				:required="required && !modelValue" :disabled="disabled" @focus="open = true; search()"
				@input="onInput" @blur="onBlur"
				@keydown="onKey" />
			<svg viewBox="0 0 24 24" class="cp-combo-caret"><path d="m7 10 5 5 5-5" /></svg>
			<Teleport to="body">
				<div v-if="open && options.length" class="cp-options cp-floating" :style="panelStyle">
					<button v-for="(row, index) in options" :key="row.name" type="button" :class="{ highlighted: index === highlighted }" @mousedown.prevent="select(row)">
						<strong>{{ projectLabel(row) }}</strong>
					</button>
				</div>
			</Teleport>
		</div>
	</label>
</template>
