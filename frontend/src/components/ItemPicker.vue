<script setup>
import { ref, watch } from "vue"
import { call } from "@/api"
import { debounce } from "@/utils"
import { useFloatingPanel } from "@/floating"

const props = defineProps({
	modelValue: { type: String, default: "" },
	label: { type: String, default: "" },
	stockableOnly: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue", "selected"])
const query = ref(props.modelValue)
const results = ref([])
const open = ref(false)
const anchor = ref(null)
const { style: panelStyle, place } = useFloatingPanel(anchor, open)

const search = debounce(async () => {
	const result = await call("get_catalog", { search: query.value, page_length: 20 })
	results.value = props.stockableOnly ? result.rows.filter((item) => item.controlled_item_type === "Stockable") : result.rows
	place()
}, 250)

function onFocus() {
	open.value = true
	search()
}

function select(item) {
	query.value = item.item_name
	open.value = false
	emit("update:modelValue", item.name)
	emit("selected", item)
}

function onBlur() {
	setTimeout(() => { open.value = false }, 150)
}

watch(() => props.modelValue, (value) => { if (!value) query.value = "" })
</script>

<template>
	<label class="cp-field">
		<span v-if="label">{{ label }}<i>*</i></span>
		<div ref="anchor" class="cp-combo">
			<input
				v-model="query"
				class="cp-input"
				placeholder="Search by description"
				:required="!modelValue"
				autocomplete="off"
				@focus="onFocus"
				@input="open = true; search()"
				@blur="onBlur"
			/>
			<svg viewBox="0 0 24 24" class="cp-combo-caret"><path d="m7 10 5 5 5-5" /></svg>
			<Teleport to="body">
			<div v-if="open && results.length" class="cp-options cp-floating" :style="panelStyle">
				<button v-for="item in results" :key="item.name" type="button" @mousedown.prevent="select(item)">
					<strong>{{ item.item_name }}</strong>
					<small>{{ item.controlled_item_type }} · {{ item.item_group }} · {{ item.name }}</small>
				</button>
			</div>
			</Teleport>
		</div>
	</label>
</template>
