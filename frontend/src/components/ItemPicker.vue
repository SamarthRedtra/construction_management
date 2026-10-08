<script setup>
import { ref, watch } from "vue"
import { call } from "@/api"
import { debounce } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	displayName: { type: String, default: "" },
	label: { type: String, default: "" },
	stockableOnly: { type: Boolean, default: false },
	showCode: { type: Boolean, default: false },
	hideCode: { type: Boolean, default: false },
	supplier: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "selected", "cleared"])
const query = ref((props.showCode ? props.modelValue : props.displayName) || props.modelValue)
const results = ref([])
const open = ref(false)
const anchor = ref(null)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)

const search = debounce(async () => {
	if (props.disabled) return
	const supplier = props.supplier
	const searched = query.value
	const result = await call("get_catalog", { search: searched, supplier, stock_only: props.stockableOnly ? 1 : 0, page_length: 20 })
	if (supplier !== props.supplier || searched !== query.value) return
	results.value = result.rows
	place()
}, 250)

function onFocus() {
	open.value = true
	search()
}

function select(item) {
	query.value = props.showCode ? item.name : item.item_name
	open.value = false
	emit("update:modelValue", item.name)
	emit("selected", item)
}

function onInput() {
	if (props.modelValue) {
		emit("update:modelValue", "")
		emit("cleared")
	}
	open.value = true
	search()
}

function onBlur() {
	setTimeout(() => { open.value = false; if (!props.modelValue) query.value = "" }, 150)
}

watch(() => [props.modelValue, props.displayName], ([code, name]) => {
	if (code) query.value = props.showCode ? code : name || code
	else if (!open.value) query.value = ""
})
watch(() => [props.supplier, props.disabled], () => { results.value = []; open.value = false })
</script>

<template>
	<label class="cp-field">
		<span v-if="label">{{ label }}<i>*</i></span>
		<div ref="anchor" class="cp-combo">
			<input
				v-model="query"
				class="cp-input"
				:placeholder="showCode ? 'Search item code or description' : 'Search by description'"
				:required="!modelValue"
				:disabled="disabled"
				autocomplete="off"
				@focus="onFocus"
				@input="onInput"
				@blur="onBlur"
			/>
			<svg viewBox="0 0 24 24" class="cp-combo-caret"><path d="m7 10 5 5 5-5" /></svg>
			<Teleport to="body">
			<div v-if="open && results.length" class="cp-options cp-floating" :style="panelStyle">
				<button v-for="item in results" :key="item.name" type="button" @mousedown.prevent="select(item)">
					<strong>{{ showCode ? item.name : item.item_name }}</strong>
					<small>{{ showCode ? item.item_name : item.controlled_item_type }} · {{ item.item_group }} · {{ item.stock_uom }}<template v-if="!hideCode"> · {{ showCode ? item.controlled_item_type : item.name }}</template></small>
				</button>
			</div>
			</Teleport>
		</div>
	</label>
</template>
