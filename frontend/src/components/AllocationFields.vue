<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { call } from "@/api"
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
	if (!props.modelValue.project) {
		bills.value = []
		items.value = []
		return
	}
	const result = await call("get_boq_options", { project: props.modelValue.project, bill_no: props.modelValue.bill_no || "" })
	bills.value = result.bills
	items.value = result.items
}

watch(() => props.modelValue.project, async (project, previous) => {
	if (project !== previous) emit("update:modelValue", { project, bill_no: "", boq_item: "" })
	await loadOptions()
})
watch(() => props.modelValue.bill_no, async () => {
	await loadOptions()
	if (props.modelValue.boq_item && !items.value.some((item) => item.name === props.modelValue.boq_item)) update("boq_item", "")
})
onMounted(loadOptions)
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
