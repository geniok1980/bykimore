"use client";
import React, { useState } from "react";
import Label from "@/components/form/Label";
import Input from "@/components/form/input/InputField";
import Button from "@/components/ui/button/Button";

import { getIikoSettings, upsertIikoSettings, testIikoConnection } from "@/lib/api";

interface IikoSettingsForm {
  serverHost: string;
  serverLogin: string;
  serverPassword: string;
}

const IikoIntegrationSettings: React.FC = () => {
  const [settings, setSettings] = useState<IikoSettingsForm>({
    serverHost: "",
    serverLogin: "",
    serverPassword: "",
  });

  const [errors, setErrors] = useState({
    serverHost: "",
    serverLogin: "",
    serverPassword: "",
  });

  const [isLoading, setIsLoading] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null); // null=не проверяли, "ok"/"error"
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);

  const validateForm = () => {
    const newErrors = {
      serverHost: "",
      serverLogin: "",
      serverPassword: "",
    };

    if (!settings.serverHost.trim()) {
      newErrors.serverHost = "Адрес сервера обязателен";
    } else if (!isValidUrl(settings.serverHost)) {
      newErrors.serverHost = "Введите корректный URL адрес";
    }
    if (!settings.serverLogin.trim()) {
      newErrors.serverLogin = "Логин обязателен";
    }
    if (!settings.serverPassword.trim()) {
      newErrors.serverPassword = "Пароль обязателен";
    }

    setErrors(newErrors);
    return Object.values(newErrors).every(error => error === "");
  };

  const isValidUrl = (url: string) => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const handleInputChange = (field: keyof IikoSettingsForm, value: string) => {
    setSettings(prev => ({
      ...prev,
      [field]: value
    }));

    // Очищаем ошибку при изменении поля
    if ((errors as any)[field]) {
      setErrors(prev => ({
        ...prev,
        [field]: ""
      }));
    }
  };

  React.useEffect(() => {
    // Загрузка сохранённых настроек из бэкенда
    (async () => {
      try {
        const s = await getIikoSettings();
        if (s) {
          setSettings({
            serverHost: s.server_host || "",
            serverLogin: s.server_login || "",
            serverPassword: s.server_password || "",
          });
          // Проверим соединение с текущими настройками
          if (s.server_host && s.server_login && s.server_password) {
            try {
              const res = await testIikoConnection();
              setConnectionStatus(res.status === "ok" ? "ok" : "error");
            } catch {
              setConnectionStatus("error");
            }
          }
          if (s.last_sync_at) {
            setLastSyncAt(s.last_sync_at);
          }
        }
      } catch (e) {
        console.warn("Не удалось загрузить iiko настройки:", e);
      }
    })();
  }, []);

  const handleSave = async () => {
    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    try {
      const saved = await upsertIikoSettings({
        server_host: settings.serverHost,
        server_login: settings.serverLogin,
        server_password: settings.serverPassword,
        active: true,
      });
      console.log("Сохранено:", saved);
      // После сохранения проверим соединение
      try {
        const res = await testIikoConnection();
        setConnectionStatus(res.status === "ok" ? "ok" : "error");
      } catch {
        setConnectionStatus("error");
      }
      alert("Настройки успешно сохранены");
    } catch (error) {
      console.error("Ошибка при сохранении настроек:", error);
      alert("Ошибка при сохранении настроек");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTestConnection = async () => {
    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    try {
      // Сохраним текущие значения перед тестом, чтобы бэкенд использовал их
      await upsertIikoSettings({
        server_host: settings.serverHost,
        server_login: settings.serverLogin,
        server_password: settings.serverPassword,
        active: true,
      });
      // Легковесный тест: бэкенд проверит доступность/авторизацию без утечки чувствительных данных
      const res = await testIikoConnection();
      setConnectionStatus("ok");
      alert(`Соединение успешно (mode=${res.mode || 'unknown'})`);
    } catch (error) {
      console.error("Ошибка при тестировании соединения:", error);
      setConnectionStatus("error");
      const msg = error instanceof Error ? (error.message || "Ошибка при тестировании соединения") : String(error);
      alert(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="p-6 border border-gray-200 rounded-2xl dark:border-gray-800 bg-white dark:bg-white/[0.03]">
        <h4 className="text-lg font-semibold text-gray-800 dark:text-white/90 mb-6">
          Настройки интеграции с iiko
        </h4>
        
        <div className="space-y-5">
          <div>
            <Label htmlFor="serverHost">Адрес iikoServer</Label>
            <Input
              id="serverHost"
              type="text"
              placeholder="https://403-115-825.iiko.it"
              defaultValue={settings.serverHost}
              onChange={(e) => handleInputChange("serverHost", e.target.value)}
              error={!!errors.serverHost}
              hint={errors.serverHost || "Введите полный URL адрес вашего iikoServer"}
            />
          </div>

          <div>
            <Label htmlFor="serverLogin">Логин</Label>
            <Input
              id="serverLogin"
              type="text"
              placeholder="admin"
              defaultValue={settings.serverLogin}
              onChange={(e) => handleInputChange("serverLogin", e.target.value)}
              error={!!errors.serverLogin}
              hint={errors.serverLogin || "Учётная запись для доступа к iikoServer"}
            />
          </div>

          <div>
            <Label htmlFor="serverPassword">Пароль</Label>
            <Input
              id="serverPassword"
              type="password"
              placeholder="Введите пароль"
              defaultValue={settings.serverPassword}
              onChange={(e) => handleInputChange("serverPassword", e.target.value)}
              error={!!errors.serverPassword}
              hint={errors.serverPassword || "Пароль для доступа к iikoServer"}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 mt-6">
          <Button 
            size="sm" 
            onClick={handleSave}
            disabled={isLoading}
          >
            {isLoading ? "Сохранение..." : "Сохранить"}
          </Button>
          
          <Button 
            size="sm" 
            variant="outline" 
            onClick={handleTestConnection}
            disabled={isLoading}
          >
            {isLoading ? "Тестирование..." : "Тестировать соединение"}
          </Button>
        </div>
      </div>

      <div className="p-6 border border-gray-200 rounded-2xl dark:border-gray-800 bg-white dark:bg-white/[0.03]">
        <h5 className="text-md font-medium text-gray-800 dark:text-white/90 mb-4">
          Информация об интеграции
        </h5>
        
        <div className="space-y-3 text-sm text-gray-600 dark:text-gray-400">
          <p>
            <strong>Статус:</strong> 
            <span className={`ml-2 px-2 py-1 rounded-full text-xs ${
              connectionStatus === "ok" 
                ? "bg-green-100 text-green-700 dark:bg-green-800/30 dark:text-green-400"
                : connectionStatus === "error"
                ? "bg-red-100 text-red-700 dark:bg-red-800/30 dark:text-red-400"
                : "bg-gray-100 dark:bg-gray-800"
            }`}>
              {connectionStatus === "ok" ? "Подключено" : connectionStatus === "error" ? "Ошибка" : "Не проверено"}
            </span>
          </p>
          
          <p>
            <strong>Последняя синхронизация:</strong> {lastSyncAt ? new Date(lastSyncAt).toLocaleString('ru-RU') : 'Никогда'}
          </p>
          
          <p>
            <strong>Версия API:</strong> v1
          </p>
        </div>
      </div>
    </div>
  );
};

export default IikoIntegrationSettings;