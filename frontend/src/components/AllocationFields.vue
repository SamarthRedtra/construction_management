<script>
import { call } from "@/api"

const OPTIONS_TTL_MS = 60000
const optionsCache = new Map()

// Module scope: the header and every line share one request per project and bill.
function boqOptions(project, billNo) {
	const key = `${project}|${billNo}`
	const cached = optionsCache.get(key)
	if (cached && Date.now() - cached.at < OPTIONS_TTL_MS) return cached.promise
	const promise = call("get_boq_options", { project, bill_no: billNo }).catch((error) => {
		optionsCache.delete(key)
		throw error
	})
	optionsCache.set(key, { at: Date.now(), promise })
	return promise
}
</script>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import ProjectSelect from "@/components/ProjectSelect.vue"

// Project is always required; boqOptional makes Bill No / BOQ Item optional (MRG, and receiving Desk POs).
const props = defineProps({ modelValue: { type: Object, required: true }, boqOptional: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue"])
const bills = ref([])
const items = ref([])
const optional = computed(() => props.boqOptional)

function update(field, value) {
	emit("update:modelValue", { ...props.modelValue, [field]: value })
}

async function loadOptions() {
	const { project, bill_no: billNo = "" } = props.modelValue
	const result = project ? await boqOptions(project, billNo || "") : { bills: [], items: [] }
	// a newer project or bill was picked while this request was in flight
	if (project !== props.modelValue.project || (billNo || "") !== (props.modelValue.bill_no || "")) return false
	bills.value = result.bills
	items.value = result.items
	return true
}

// Keep saved values that belong to the loaded project; clear only the ones that no longer apply.
async function syncSelection() {
	if (!(await loadOptions())) return
	const { bill_no: billNo, boq_item: boqItem } = props.modelValue
	if (billNo && !bills.value.some((bill) => bill.name === billNo)) {
		emit("update:modelValue", { ...props.modelValue, bill_no: "", boq_item: "" })
	} else if (boqItem && !items.value.some((item) => item.name === boqItem)) {
		update("boq_item", "")
	}
}

watch(() => [props.modelValue.project, props.modelValue.bill_no], syncSelection)
onMounted(syncSelection)
</script>

<template>
	<div class="cp-grid-3">
		<ProjectSelect :model-value="modelValue.project" :required="true" @update:model-value="update('project', $event)" />
		<label class="cp-field">
			<span>Bill No<i v-if="!optional">*</i></span>
			<select class="cp-input" :value="modelValue.bill_no" :disabled="!modelValue.project" :required="!optional" @change="update('bill_no', $event.target.value)">
				<option value="">{{ !modelValue.project ? "Select a project first" : optional ? "Optional" : "Select Bill No" }}</option>
				<option v-for="bill in bills" :key="bill.name" :value="bill.name">{{ bill.bill_no || bill.name }}</option>
			</select>
		</label>
		<label class="cp-field">
			<span>BOQ Item<i v-if="!optional">*</i></span>
			<select class="cp-input" :value="modelValue.boq_item" :disabled="!modelValue.bill_no" :required="!optional" @change="update('boq_item', $event.target.value)">
				<option value="">{{ !modelValue.bill_no ? (optional ? "Optional — select a bill first" : "Select a bill first") : optional ? "Optional" : "Select BOQ Item" }}</option>
				<option v-for="item in items" :key="item.name" :value="item.name">{{ item.description || item.name }}</option>
			</select>
		</label>
	</div>
</template>
