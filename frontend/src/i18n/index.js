import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './en.json';
import hi from './hi.json';
import kn from './kn.json';

const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('pramaan_lang') : null;

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi }, kn: { translation: kn } },
  lng: saved || 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export default i18n;
