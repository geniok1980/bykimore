"use client";
import { useState } from "react";
import SettingsCard from "../../../../components/settings/SettingsCard";
import TabNavigation, { TabType } from "../../../../components/settings/TabNavigation";
import IikoIntegrationSettings from "../../../../components/settings/IikoIntegrationSettings";
import UsersManagement from "../../../../components/users/UsersManagement";
import { useAuth } from "../../../../hooks/useAuth";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

const Settings = () => {
  const [activeTab, setActiveTab] = useState<TabType>("general");
  const { isAdmin, isAuthenticated } = useAuth();
  const router = useRouter();

  // Модалка для GENERAL tab (SettingsCard)
  const [isOpenSettingsModal, setIsOpenSettingsModal] = useState(false);
  const [currentSettingsItem, setCurrentSettingsItem] = useState<any>(null);
  const [blockClose, setBlockClose] = useState(false);
  const [settingsModalErrors, setSettingsModalErrors] = useState<any>({});

  useEffect(() => {
    if (activeTab === "users" && isAuthenticated !== null && !isAdmin) {
      router.push("/");
    }
  }, [activeTab, isAdmin, isAuthenticated, router]);

  const renderTabContent = () => {
    switch (activeTab) {
      case "general":
        return <SettingsCard 
          modalProps={{
            isOpen: isOpenSettingsModal,
            setIsOpen: setIsOpenSettingsModal,
            currentItem: currentSettingsItem,
            setCurrentItem: setCurrentSettingsItem,
            blockClose,
            setBlockClose,
            errors: settingsModalErrors,
            setErrors: setSettingsModalErrors,
          }}
        />
      case "iiko-integration":
        return <IikoIntegrationSettings />;
      case "users":
        return <UsersManagement />;
      default:
        return null;
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-800 dark:text-white/90 mb-6">
        Настройки
      </h1>
      
      <TabNavigation 
        activeTab={activeTab} 
        onTabChange={setActiveTab} 
      />
      
      <div className="mt-6">
        {renderTabContent()}
      </div>
    </div>
  );
};

export default Settings;