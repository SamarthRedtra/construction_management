import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import path from "path"

export default defineConfig(({ command }) => ({
	// production assets are served by Frappe from the app's public folder
	base: command === "build" ? "/assets/construction_management/controlled_procurement/" : "/",
	plugins: [vue()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	server: {
		proxy: {
			"^/(api|assets|files|private|login|app|desk)": "http://localhost:8002",
		},
	},
	build: {
		outDir: "../construction_management/public/controlled_procurement",
		emptyOutDir: true,
		manifest: true,
		target: "es2018",
		rollupOptions: {
			input: "index.html",
		},
	},
}))
