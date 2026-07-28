"use client";
import React, { useRef, useEffect } from "react";
import { useModal } from "../../hooks/useModal";
import { Modal } from "../ui/modal/index";
import Button from "../ui/button/Button";
import { Combobox } from "@headlessui/react";
import Label from "../form/Label";
import { Dish, listBeerExchangeSettings, upsertBeerExchangeSettings, deleteDish, IikoProduct, getIikoProducts, createDish, syncSales, startAutoSync, stopAutoSync, getAutoSyncStatus } from "@/lib/api";
import { getDishes } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";

interface SettingItem {
  id: number;
  dishId: number;
  title: string;
  description: string;
  salesQuantity: number;
  weightGrams: number;
  active: boolean;
}

interface ModalProps {
  isOpen: boolean;
  setIsOpen: (v: boolean) => void;
  currentItem: any;
  setCurrentItem: (v: any) => void;
  blockClose: boolean;
  setBlockClose: (v: boolean) => void;
  errors: any;
  setErrors: (v: any) => void;
}

function todayStr() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}
function daysAgoStr(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

export default function SettingsCard({ modalProps }: { modalProps: ModalProps }) {
  const [settings, setSettings] = React.useState<any[]>([]);
  const [dishes, setDishes] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState<boolean>(true);
  const [loadError, setLoadError] = React.useState<string>("");

  // Синхронизация
  const [syncLoading, setSyncLoading] = React.useState<boolean>(false);
  const [syncMessage, setSyncMessage] = React.useState<string>("");
  const [syncError, setSyncError] = React.useState<string>("");
  const [showSyncModal, setShowSyncModal] = React.useState<boolean>(false);
  const [syncDateFrom, setSyncDateFrom] = React.useState(daysAgoStr(30));
  const [syncDateTo, setSyncDateTo] = React.useState(todayStr());
  const [syncDone, setSyncDone] = React.useState<boolean>(false);

  // Автосинхронизация
  const [autoSyncEnabled, setAutoSyncEnabled] = React.useState<boolean>(false);
  const [autoSyncDateFrom, setAutoSyncDateFrom] = React.useState<string>("");
  const [autoSyncTaskRunning, setAutoSyncTaskRunning] = React.useState<boolean>(false);
  const [autoSyncLoading, setAutoSyncLoading] = React.useState<boolean>(false);

  const { isAdmin, isAuthenticated } = useAuth();
  const dateFromRef = useRef<HTMLInputElement>(null);
  const dateToRef = useRef<HTMLInputElement>(null);
  const dishRef = useRef<HTMLInputElement>(null);
  const [dishQuery, setDishQuery] = React.useState("");
  const [selectedDish, setSelectedDish] = React.useState<any>(null);
  const [iikoProducts, setIikoProducts] = React.useState<any[]>([]);
  const [iikoLoading, setIikoLoading] = React.useState<boolean>(false);
  const [iikoError, setIikoError] = React.useState<string>("");
  const [selectedIikoProduct, setSelectedIikoProduct] = React.useState<any>(null);
  const salesQtyRef = useRef<HTMLInputElement>(null);
  const weightGramsRef = useRef<HTMLInputElement>(null);

  const openModal = () => modalProps.setIsOpen(true);
  const closeModal = () => modalProps.setIsOpen(false);

  const errors = modalProps.errors;
  const setErrors = modalProps.setErrors;
  const blockClose = modalProps.blockClose;
  const setBlockClose = modalProps.setBlockClose;
  const currentItem = modalProps.currentItem;
  const setCurrentItem = modalProps.setCurrentItem;

  // Загрузка настроек
  useEffect(() => {
    if (isAuthenticated === null) return;
    if (isAuthenticated === false) {
      setLoading(false);
      setLoadError("Для загрузки настроек сначала выполните вход.");
      return;
    }
    const load = async () => {
      try {
        setLoading(true);
        setLoadError("");
        const [dishesRes, settingsRes] = await Promise.all([
          getDishes(),
          listBeerExchangeSettings(),
        ]);
        setDishes(dishesRes);
        const items: SettingItem[] = settingsRes.map((s) => {
          const dishName = dishesRes.find((d) => d.id === s.dish_id)?.name ?? `Блюдо #${s.dish_id}`;
          return {
            id: s.id,
            dishId: s.dish_id,
            title: dishName,
            description: "Настройки для блюда",
            salesQuantity: s.sales_quantity ?? 0,
            weightGrams: s.weight_grams ?? 0,
            active: s.active,
          };
        });
        setSettings(items);
      } catch (e: any) {
        setLoadError(e?.message || "Не удалось загрузить настройки");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [isAuthenticated]);

  // Статус автосинхронизации
  useEffect(() => {
    if (!isAdmin) return;
    getAutoSyncStatus().then((st) => {
      setAutoSyncEnabled(st.enabled);
      setAutoSyncDateFrom(st.date_from || "");
      setAutoSyncTaskRunning(st.task_running);
    }).catch(() => {});
  }, [isAdmin]);

  useEffect(() => {
    if (!modalProps.isOpen || !isAdmin) return;
    const loadIiko = async () => {
      try {
        setIikoLoading(true);
        setIikoError("");
        const products = await getIikoProducts();
        setIikoProducts(products);
      } catch (e: any) {
        setIikoError(e?.message || "Не удалось загрузить продукты из iiko");
      } finally {
        setIikoLoading(false);
      }
    };
    loadIiko();
  }, [modalProps.isOpen, isAdmin]);

  const validateForm = () => {
    const newErrors: Record<string, string> = { dish: "", salesQuantity: "" };
    const dish = dishRef.current?.value || "";
    const salesQuantity = Number(salesQtyRef.current?.value || 0);
    if (!dish.trim()) newErrors.dish = "Название блюда обязательно";
    if (salesQuantity < 0 || !Number.isInteger(salesQuantity)) newErrors.salesQuantity = "Количество продаж должно быть целым числом и не меньше 0";
    setErrors(newErrors);
    return Object.values(newErrors).every(error => error === "");
  };

  const handleSave = async () => {
    if (!validateForm()) return;
    if (currentItem) {
      const dishName = dishRef.current?.value || "";
      const salesQuantity = Number(salesQtyRef.current?.value || 0);
      const weightGrams = Number(weightGramsRef.current?.value || 0);
      try {
        let selectedDish = dishes.find(d => d.name === dishName) || dishes.find(d => d.id === currentItem.dishId) || null;
        if (!selectedDish && selectedIikoProduct && (selectedIikoProduct.name || "") === dishName) {
          const created = await createDish({ name: selectedIikoProduct.name || dishName, initial_price: selectedIikoProduct.price ?? undefined });
          selectedDish = created;
          setDishes(prev => [...prev, created]);
        }
        if (!selectedDish) {
          setErrors((prev: typeof errors) => ({ ...prev, dish: "Выберите блюдо из списка или из iiko" }));
          return;
        }
        const updated = await upsertBeerExchangeSettings({
          dish_id: selectedDish.id,
          sales_quantity: salesQuantity,
          weight_grams: weightGrams,
          active: currentItem.active,
        });
        const dishTitle = dishes.find(d => d.id === updated.dish_id)?.name ?? dishName;
        setSettings(prev => {
          const existsIndex = prev.findIndex(i => i.dishId === updated.dish_id);
          const newItem: SettingItem = {
            id: updated.id,
            dishId: updated.dish_id,
            title: dishTitle,
            description: "Настройки для блюда",
            salesQuantity: updated.sales_quantity ?? 0,
            weightGrams: updated.weight_grams ?? 0,
            active: updated.active,
          };
          if (existsIndex >= 0) {
            const copy = [...prev];
            copy[existsIndex] = newItem;
            return copy;
          }
          return [...prev, newItem];
        });
        setSelectedIikoProduct(null);
        setBlockClose(false);
        closeModal();
      } catch (e: any) {
        setErrors((prev: typeof errors) => ({ ...prev, dish: e?.message || "Ошибка сохранения" }));
        setBlockClose(true);
      }
    }
  };

  const clearError = (field: string) => {
    if (errors[field]) {
      setErrors((prev: typeof errors) => ({ ...prev, [field]: "" }));
    }
  };

  const handleDeleteDish = async (item: SettingItem) => {
    if (!isAdmin) return;
    const confirmed = typeof window !== "undefined" ? window.confirm(`Удалить блюдо "${item.title}" и все связанные данные?`) : true;
    if (!confirmed) return;
    try {
      await deleteDish(item.dishId);
      setSettings(prev => prev.filter(s => s.dishId !== item.dishId));
      setDishes(prev => prev.filter(d => d.id !== item.dishId));
      if (selectedDish?.id === item.dishId) {
        setSelectedDish(null);
        setDishQuery("");
        if (dishRef.current) dishRef.current.value = "";
      }
    } catch (e: any) {
      const msg = e?.message || "Не удалось удалить блюдо";
      if (typeof window !== "undefined") alert(msg);
      else console.error(msg);
    }
  };

  // --- Обработчики синхронизации ---
  const doSync = async (dateFrom: string, dateTo: string) => {
    setSyncLoading(true);
    setSyncMessage("");
    setSyncError("");
    setSyncDone(false);
    try {
      const res = await syncSales(dateFrom, dateTo);
      setSyncMessage(res.message);
      setSyncDone(true);
      // Перезагружаем настройки чтобы увидеть новые значения
      const [dishesRes, settingsRes] = await Promise.all([getDishes(), listBeerExchangeSettings()]);
      setDishes(dishesRes);
      const items: SettingItem[] = settingsRes.map((s) => {
        const dishName = dishesRes.find((d) => d.id === s.dish_id)?.name ?? `Блюдо #${s.dish_id}`;
        return {
          id: s.id,
          dishId: s.dish_id,
          title: dishName,
          description: "Настройки для блюда",
          salesQuantity: s.sales_quantity ?? 0,
          weightGrams: s.weight_grams ?? 0,
          active: s.active,
        };
      });
      setSettings(items);
    } catch (e: any) {
      setSyncError(e?.message || "Ошибка синхронизации");
    } finally {
      setSyncLoading(false);
    }
  };

  const handleStartAutoSync = async () => {
    setAutoSyncLoading(true);
    try {
      const st = await startAutoSync(syncDateFrom);
      setAutoSyncEnabled(st.enabled);
      setAutoSyncDateFrom(st.date_from || "");
      setAutoSyncTaskRunning(st.task_running);
    } catch (e: any) {
      setSyncError(e?.message || "Ошибка запуска автосинхронизации");
    } finally {
      setAutoSyncLoading(false);
    }
  };

  const handleStopAutoSync = async () => {
    setAutoSyncLoading(true);
    try {
      await stopAutoSync();
      setAutoSyncEnabled(false);
      setAutoSyncTaskRunning(false);
    } catch (e: any) {
      setSyncError(e?.message || "Ошибка остановки автосинхронизации");
    } finally {
      setAutoSyncLoading(false);
    }
  };

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <div className="flex flex-wrap gap-2 items-center">
          {loading && <span className="text-sm text-gray-500 dark:text-gray-400">Загрузка настроек…</span>}
          {loadError && <span className="text-sm text-red-600">{loadError}</span>}
          {syncMessage && <span className="text-sm text-green-700">{syncMessage}</span>}
          {syncError && <span className="text-sm text-red-600">{syncError}</span>}
          {autoSyncEnabled && (
            <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
              Автосинхронизация каждые 5 мин
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <Button
            size="sm"
            onClick={() => setShowSyncModal(true)}
            disabled={!isAdmin || syncLoading}
          >
            {syncLoading ? "Синхронизация…" : "Синхронизировать продажи"}
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setCurrentItem({
                id: 0,
                dishId: 0,
                title: "",
                description: "Настройки для блюда",
                salesQuantity: 0,
                weightGrams: 0,
                active: true,
              });
              setErrors({ dish: "", salesQuantity: "" });
              openModal();
            }}
            disabled={!isAdmin}
          >
            Добавить блюдо
          </Button>
        </div>
      </div>

      {/* Модалка выбора периода синхронизации */}
      <Modal isOpen={showSyncModal} onClose={() => { if (!syncLoading) setShowSyncModal(false); }} persistent className="max-w-[500px] m-4">
        <div className="no-scrollbar relative w-full max-w-[500px] rounded-3xl bg-white p-6 dark:bg-gray-900">
          <h4 className="mb-4 text-xl font-semibold text-gray-800 dark:text-white/90">
            Синхронизация продаж
          </h4>

          <div className="mb-4">
            <Label>Период синхронизации</Label>
            <div className="flex flex-wrap gap-2 mt-2 mb-3">
              <button
                type="button"
                className={`px-3 py-1.5 text-sm rounded-lg border ${syncDateFrom === daysAgoStr(7) ? "bg-brand-500 text-white border-brand-500" : "bg-white text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300"}`}
                onClick={() => { setSyncDateFrom(daysAgoStr(7)); setSyncDateTo(todayStr()); }}
              >7 дней</button>
              <button
                type="button"
                className={`px-3 py-1.5 text-sm rounded-lg border ${syncDateFrom === daysAgoStr(30) ? "bg-brand-500 text-white border-brand-500" : "bg-white text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300"}`}
                onClick={() => { setSyncDateFrom(daysAgoStr(30)); setSyncDateTo(todayStr()); }}
              >30 дней</button>
              <button
                type="button"
                className={`px-3 py-1.5 text-sm rounded-lg border ${syncDateFrom === daysAgoStr(90) ? "bg-brand-500 text-white border-brand-500" : "bg-white text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300"}`}
                onClick={() => { setSyncDateFrom(daysAgoStr(90)); setSyncDateTo(todayStr()); }}
              >90 дней</button>
              <button
                type="button"
                className={`px-3 py-1.5 text-sm rounded-lg border ${syncDateFrom === daysAgoStr(365) ? "bg-brand-500 text-white border-brand-500" : "bg-white text-gray-700 border-gray-300 dark:bg-gray-800 dark:text-gray-300"}`}
                onClick={() => { setSyncDateFrom(daysAgoStr(365)); setSyncDateTo(todayStr()); }}
              >Год</button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>С</Label>
                <div className="relative">
                  <div onClick={() => dateFromRef.current?.showPicker()}
                    className="flex items-center gap-2 h-10 w-full rounded-lg border px-3 text-sm bg-transparent text-gray-800 border-gray-300 dark:border-gray-700 dark:text-white/90 cursor-pointer"
                  >
                    <svg className="w-4 h-4 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span>{syncDateFrom.replace(/-/g, '.')}</span>
                  </div>
                  <input type="date" value={syncDateFrom}
                    onChange={(e) => setSyncDateFrom(e.target.value)}
                    ref={dateFromRef}
                    className="absolute top-0 left-0 w-0 h-0 opacity-0 pointer-events-none"
                  />
                </div>
              </div>
              <div>
                <Label>По</Label>
                <div className="relative">
                  <div onClick={() => dateToRef.current?.showPicker()}
                    className="flex items-center gap-2 h-10 w-full rounded-lg border px-3 text-sm bg-transparent text-gray-800 border-gray-300 dark:border-gray-700 dark:text-white/90 cursor-pointer"
                  >
                    <svg className="w-4 h-4 text-gray-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span>{syncDateTo.replace(/-/g, '.')}</span>
                  </div>
                  <input type="date" value={syncDateTo}
                    onChange={(e) => setSyncDateTo(e.target.value)}
                    ref={dateToRef}
                    className="absolute top-0 left-0 w-0 h-0 opacity-0 pointer-events-none"
                  />
                </div>
              </div>
            </div>
          </div>

          {syncMessage && <p className="text-sm text-green-700 mb-3">{syncMessage}</p>}
          {syncError && <p className="text-sm text-red-600 mb-3">{syncError}</p>}

          <div className="flex items-center gap-3 justify-end mt-6">
            <Button size="sm" variant="outline" onClick={() => setShowSyncModal(false)} disabled={syncLoading}>
              Закрыть
            </Button>
            <Button size="sm" onClick={() => doSync(syncDateFrom, syncDateTo)} disabled={syncLoading}>
              {syncLoading ? "Синхронизация…" : "Синхронизировать"}
            </Button>
          </div>

          {/* Автосинхронизация — показываем после успешной синхронизации */}
          {syncDone && (
            <div className="mt-5 pt-4 border-t border-gray-200 dark:border-gray-700">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Автоматическая синхронизация каждые 5 минут
              </p>
              {!autoSyncEnabled ? (
                <Button size="sm" onClick={handleStartAutoSync} disabled={autoSyncLoading}>
                  {autoSyncLoading ? "Запуск…" : "Запустить автосинхронизацию"}
                </Button>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="text-xs text-blue-700 bg-blue-100 px-2 py-0.5 rounded">
                    Активно (с {autoSyncDateFrom})
                  </span>
                  <Button size="sm" variant="outline" onClick={handleStopAutoSync} disabled={autoSyncLoading}>
                    Остановить
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>

      {/* Карточки блюд */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {settings.map((item, index) => (
          <div key={item.id} className="p-5 border border-gray-200 rounded-2xl dark:border-gray-800 lg:p-6">
            <div className="flex flex-col gap-4">
              <div>
                <h4 className="text-lg font-semibold text-gray-800 dark:text-white/90 mb-2">
                  {index + 1}. {item.title}
                </h4>
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{item.description}</p>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Блюдо:</span>
                    <span className="text-sm font-medium text-gray-800 dark:text-white/90">{item.title}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Количество продаж:</span>
                    <span className="text-sm font-medium text-gray-800 dark:text-white/90">{item.salesQuantity}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Вес порции:</span>
                    <span className="text-sm font-medium text-gray-800 dark:text-white/90">{item.weightGrams ? `${item.weightGrams} г` : "—"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-xs text-gray-500 dark:text-gray-400">Активность:</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${item.active ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>
                      {item.active ? "Активно" : "Выключено"}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex justify-end">
                <button
                  onClick={() => handleDeleteDish(item)}
                  className="ml-2 flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-800 transition-colors"
                  disabled={!isAdmin}
                  title="Удалить блюдо"
                >
                  <svg className="w-4 h-4" width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M6 2.25C6 1.83579 6.33579 1.5 6.75 1.5H11.25C11.6642 1.5 12 1.83579 12 2.25V3H15C15.4142 3 15.75 3.33579 15.75 3.75C15.75 4.16421 15.4142 4.5 15 4.5H3C2.58579 4.5 2.25 4.16421 2.25 3.75C2.25 3.33579 2.58579 3 3 3H6V2.25ZM4.5 6H13.5L12.9393 14.0303C12.9007 14.6046 12.417 15 11.8417 15H6.1583C5.58304 15 5.0993 14.6046 5.06066 14.0303L4.5 6Z" fill="currentColor"/>
                  </svg>
                  Удалить блюдо
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <Modal isOpen={modalProps.isOpen} onClose={() => { if (!blockClose) closeModal(); }} persistent className="max-w-[600px] m-4">
        <div className="no-scrollbar relative w-full max-w-[600px] overflow-y-auto rounded-3xl bg-white p-4 dark:bg-gray-900 lg:p-8">
          <div className="px-2 pr-14">
            <h4 className="mb-2 text-2xl font-semibold text-gray-800 dark:text-white/90">Редактировать настройки</h4>
            <p className="mb-6 text-sm text-gray-500 dark:text-gray-400 lg:mb-7">{currentItem?.title} - {currentItem?.description}</p>
          </div>
          <form className="flex flex-col" onSubmit={(e) => { e.preventDefault(); }}>
            <div className="px-2 pb-3">
              <div className="space-y-5">
                <div>
                  <Label>Блюдо</Label>
                  <Combobox
                    value={selectedIikoProduct}
                    onChange={(p: IikoProduct | null) => {
                      setSelectedIikoProduct(p);
                      setSelectedDish(null);
                      const name = p?.name || dishRef.current?.value || "";
                      setDishQuery(name);
                      if (p && dishRef.current) { dishRef.current.value = name; }
                      clearError('dish');
                    }}
                  >
                    <div className="relative">
                      <Combobox.Input
                        ref={dishRef as any}
                        placeholder="Начните вводить название или артикул"
                        autoComplete="off"
                        className={`h-11 w-full rounded-lg border appearance-none px-4 py-2.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:outline-hidden focus:ring-3 bg-transparent text-gray-800 border-gray-300 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 ${errors.dish ? "border-red-500" : ""}`}
                        displayValue={(p: IikoProduct | null) => p?.name || dishQuery || currentItem?.title || ""}
                        onChange={(e) => {
                          setDishQuery(e.target.value);
                          setSelectedDish(null);
                          setSelectedIikoProduct(null);
                          clearError('dish');
                        }}
                      />
                      <Combobox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-gray-200 bg-white py-1 text-sm shadow-lg dark:border-gray-700 dark:bg-gray-800">
                        {(dishQuery.trim() ? iikoProducts.filter((p) => {
                          const q = dishQuery.trim().toLowerCase();
                          const name = (p.name || "").toLowerCase();
                          const code = (p.code || "").toLowerCase();
                          return name.includes(q) || (code && code.includes(q));
                        }).slice(0, 50) : []).map((p) => (
                          <Combobox.Option key={p.id ?? p.name} value={p}
                            className={({ active }) => `cursor-pointer select-none px-4 py-2 ${active ? 'bg-gray-100 dark:bg-gray-700' : ''}`}
                          >
                            {(() => {
                              const parsed = Number(p.price);
                              const priceToShow = Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
                              return (
                                <div className="flex items-center justify-between">
                                  <span>{p.name}{p.code ? ` — Артикул: ${p.code}` : ""}</span>
                                  <span className="text-gray-500 dark:text-gray-400">
                                    {new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", minimumFractionDigits: 0 }).format(priceToShow)}
                                  </span>
                                </div>
                              );
                            })()}
                          </Combobox.Option>
                        ))}
                        {dishQuery.trim().length === 0 ? (
                          <div className="px-4 py-2 text-gray-500 dark:text-gray-300">Начните вводить название или артикул</div>
                        ) : (iikoProducts.filter((p) => {
                          const q = dishQuery.trim().toLowerCase();
                          const name = (p.name || "").toLowerCase();
                          const code = (p.code || "").toLowerCase();
                          return name.includes(q) || (code && code.includes(q));
                        }).length === 0 ? (
                          <div className="px-4 py-2 text-gray-500 dark:text-gray-300">Ничего не найдено</div>
                        ) : null)}
                      </Combobox.Options>
                    </div>
                  </Combobox>
                  {errors.dish && <p className="mt-1 text-sm text-red-500">{errors.dish}</p>}
                </div>

                <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
                  <div>
                    <Label>Количество продаж</Label>
                    <input
                      ref={salesQtyRef} type="number"
                      defaultValue={currentItem?.salesQuantity || 0}
                      onChange={() => clearError('salesQuantity')}
                      placeholder="0" min="0" step="1"
                      className={`h-11 w-full rounded-lg border appearance-none px-4 py-2.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:outline-hidden focus:ring-3 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 dark:focus:border-brand-800 bg-transparent text-gray-800 border-gray-300 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800 ${errors.salesQuantity ? "border-red-500" : ""}`}
                    />
                    {errors.salesQuantity && <p className="mt-1 text-sm text-red-500">{errors.salesQuantity}</p>}
                  </div>
                  <div>
                    <Label>Вес порции (граммы)</Label>
                    <input
                      ref={weightGramsRef} type="number"
                      defaultValue={currentItem?.weightGrams || 0}
                      placeholder="0" min="0" step="1"
                      className="h-11 w-full rounded-lg border appearance-none px-4 py-2.5 text-sm shadow-theme-xs placeholder:text-gray-400 focus:outline-hidden focus:ring-3 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30 dark:focus:border-brand-800 bg-transparent text-gray-800 border-gray-300 focus:border-brand-300 focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:focus:border-brand-800"
                    />
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3 px-2 mt-6 lg:justify-end">
              <Button size="sm" variant="outline" onClick={() => { setBlockClose(false); closeModal(); }}>Отмена</Button>
              <Button size="sm" onClick={handleSave} disabled={!isAdmin}>Сохранить</Button>
            </div>
          </form>
        </div>
      </Modal>
    </>
  );
}
