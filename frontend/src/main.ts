import { createApp } from 'vue'
import App from '@/App.vue'
import { bootstrap } from '@/boot'
import '@fontsource-variable/inter'
import '@/assets/main.css'

void bootstrap(createApp(App))
