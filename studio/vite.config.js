import {defineConfig} from 'vite';
export default defineConfig({server:{host:'127.0.0.1',port:2720,proxy:{'/api':process.env.CADFORGE_API_URL||'http://127.0.0.1:2721'}},build:{outDir:'dist'}});
