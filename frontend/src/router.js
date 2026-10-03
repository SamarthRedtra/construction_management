import { createRouter, createWebHistory } from "vue-router"

const routes = [
	{ path: "/", redirect: "/dashboard" },
	{ path: "/dashboard", name: "dashboard", component: () => import("@/views/DashboardView.vue") },
	{ path: "/open-lpos", name: "open-lpos", component: () => import("@/views/OpenLposView.vue") },
	{ path: "/purchase-orders", name: "orders", component: () => import("@/views/DocumentListView.vue"), props: { kind: "orders" } },
	{ path: "/purchase-orders/new", name: "order-new", component: () => import("@/views/PurchaseOrderForm.vue") },
	{ path: "/purchase-orders/:name/edit", name: "order-edit", component: () => import("@/views/PurchaseOrderForm.vue"), props: (route) => ({ name: route.params.name }) },
	{ path: "/purchase-orders/:name", name: "order", component: () => import("@/views/DocumentDetailView.vue"), props: (route) => ({ kind: "orders", docname: route.params.name }) },
	{ path: "/lpo-approvals", name: "lpo-approvals", component: () => import("@/views/LpoApprovalsView.vue") },
	{ path: "/insights", name: "insights", component: () => import("@/views/ProcurementInsightsView.vue") },
	{ path: "/stock-ledger", name: "stock-ledger", component: () => import("@/views/ProcurementStockLedgerView.vue") },
	{ path: "/receipts", name: "receipts", component: () => import("@/views/DocumentListView.vue"), props: { kind: "receipts" } },
	{ path: "/receipts/new", name: "receipt-new", component: () => import("@/views/PurchaseReceiptForm.vue") },
	{ path: "/receipts/:name/edit", name: "receipt-edit", component: () => import("@/views/PurchaseReceiptForm.vue"), props: (route) => ({ name: route.params.name }) },
	{ path: "/receipts/:name", name: "receipt", component: () => import("@/views/DocumentDetailView.vue"), props: (route) => ({ kind: "receipts", docname: route.params.name }) },
	{ path: "/invoices", name: "invoices", component: () => import("@/views/DocumentListView.vue"), props: { kind: "invoices" } },
	{ path: "/invoices/new", name: "invoice-new", component: () => import("@/views/PurchaseInvoiceForm.vue") },
	{ path: "/invoices/:name", name: "invoice", component: () => import("@/views/DocumentDetailView.vue"), props: (route) => ({ kind: "invoices", docname: route.params.name }) },
	{ path: "/transfers", name: "transfers", component: () => import("@/views/DocumentListView.vue"), props: { kind: "transfers" } },
	{ path: "/transfers/new", name: "transfer-new", component: () => import("@/views/TransferForm.vue") },
	{ path: "/transfers/:name/edit", name: "transfer-edit", component: () => import("@/views/TransferForm.vue"), props: (route) => ({ name: route.params.name }) },
	{ path: "/transfers/:name", name: "transfer", component: () => import("@/views/DocumentDetailView.vue"), props: (route) => ({ kind: "transfers", docname: route.params.name }) },
	{ path: "/catalog", name: "catalog", component: () => import("@/views/CatalogView.vue") },
	{ path: "/catalog/approvals", name: "catalog-approvals", component: () => import("@/views/CatalogApprovalsView.vue") },
	{ path: "/catalog/prices", name: "catalog-prices", component: () => import("@/views/PriceRequestsView.vue") },
	{ path: "/:pathMatch(.*)*", redirect: "/dashboard" },
]

export default createRouter({
	history: createWebHistory("/procurement"),
	routes,
	scrollBehavior: () => ({ top: 0 }),
})
