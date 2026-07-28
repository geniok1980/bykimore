"use client";
import React, { useState, useEffect } from "react";
import { getAllUsers, createUser, updateUser, deleteUser, UserCreateRequest, User } from "@/lib/api";
import Button from "../ui/button/Button";
import Input from "../form/input/InputField";
import Label from "../form/Label";
import { Modal } from "../ui/modal/index";
import { useModal } from "@/hooks/useModal";
import { TrashBinIcon, PencilIcon } from "@/icons";

export default function UsersManagement() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const createModal = useModal();
  const editModal = useModal();
  const [editingUser, setEditingUser] = useState<User | null>(null);
  
  const [formData, setFormData] = useState<Omit<UserCreateRequest, "tenant_id">>({
    username: "",
    password: "",
    role: "user",
  });

  useEffect(() => {
    loadUsers();
  }, []);

  const loadUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAllUsers();
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    
    try {
      await createUser({ ...formData, tenant_id: "default" });
      createModal.closeModal();
      setFormData({ username: "", password: "", role: "user" });
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create user");
    }
  };

  const handleEdit = (user: User) => {
    setEditingUser(user);
    setFormData({
      username: user.username,
      password: "",
      role: user.role,
    });
    editModal.openModal();
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingUser) return;
    
    setError(null);
    
    try {
      await updateUser(editingUser.id, { ...formData, tenant_id: "default" });
      editModal.closeModal();
      setEditingUser(null);
      setFormData({ username: "", password: "", role: "user" });
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update user");
    }
  };

  const handleDelete = async (userId: number) => {
    if (!confirm("Вы уверены, что хотите удалить этого пользователя?")) return;
    
    try {
      await deleteUser(userId);
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete user");
    }
  };

  const getRoleBadge = (role: string) => {
    const colors: { [key: string]: string } = {
      superadmin: "bg-red-500",
      admin: "bg-blue-500",
      user: "bg-gray-500",
    };
    
    return (
      <span className={`px-2 py-1 rounded-full text-xs text-white ${colors[role] || "bg-gray-500"}`}>
        {role}
      </span>
    );
  };

  return (
    <div className="p-5 border border-gray-200 rounded-2xl dark:border-gray-800">
      <div className="flex justify-between items-center mb-6">
        <h4 className="text-lg font-semibold text-gray-800 dark:text-white/90">
          Управление пользователями
        </h4>
        <Button onClick={createModal.openModal}>Создать пользователя</Button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center py-8">Загрузка...</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-800">
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-600 dark:text-gray-400">ID</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-600 dark:text-gray-400">Имя</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-600 dark:text-gray-400">Tenant</th>
                <th className="text-left py-3 px-4 text-sm font-medium text-gray-600 dark:text-gray-400">Роль</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-gray-600 dark:text-gray-400">Действия</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="border-b border-gray-200 dark:border-gray-800">
                  <td className="py-3 px-4 text-sm text-gray-800 dark:text-white/90">{user.id}</td>
                  <td className="py-3 px-4 text-sm text-gray-800 dark:text-white/90">{user.username}</td>
                  <td className="py-3 px-4 text-sm text-gray-800 dark:text-white/90">{user.tenant_id}</td>
                  <td className="py-3 px-4">{getRoleBadge(user.role)}</td>
                  <td className="py-3 px-4">
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => handleEdit(user)}
                        className="p-2 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                        title="Редактировать"
                      >
                        <PencilIcon className="w-5 h-5" />
                      </button>
                      <button
                        onClick={() => handleDelete(user.id)}
                        className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="Удалить"
                      >
                        <TrashBinIcon className="w-5 h-5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create Modal */}
      <Modal
        isOpen={createModal.isOpen}
        onClose={createModal.closeModal}
      >
        <h3 className="px-6 pt-6 text-lg font-semibold text-gray-800 dark:text-white/90">
          Создать пользователя
        </h3>
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <Label htmlFor="username">Имя пользователя</Label>
            <Input
              id="username"
              defaultValue={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="password">Пароль</Label>
            <Input
              id="password"
              type="password"
              defaultValue={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
          </div>
          {/* Tenant ID input and label удаляются из формы */}
          <div>
            <Label htmlFor="role">Роль</Label>
            <select
              id="role"
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
              required
            >
              <option value="user">Пользователь</option>
              <option value="admin">Администратор</option>
              <option value="superadmin">Суперадмин</option>
            </select>
          </div>
          <div className="flex justify-end gap-3">
            <Button type="button" onClick={createModal.closeModal} variant="secondary">
              Отмена
            </Button>
            <Button type="submit">Создать</Button>
          </div>
        </form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        isOpen={editModal.isOpen}
        onClose={editModal.closeModal}
      >
        <h3 className="px-6 pt-6 text-lg font-semibold text-gray-800 dark:text-white/90">
          Редактировать пользователя
        </h3>
        <form onSubmit={handleUpdate} className="space-y-4">
          <div>
            <Label htmlFor="edit_username">Имя пользователя</Label>
            <Input
              id="edit_username"
              defaultValue={formData.username}
              onChange={(e) => setFormData({ ...formData, username: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="edit_password">Пароль (оставьте пустым, чтобы не менять)</Label>
            <Input
              id="edit_password"
              type="password"
              defaultValue={formData.password}
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
          </div>
          {/* Tenant ID input и label удаляются из формы */}
          <div>
            <Label htmlFor="edit_role">Роль</Label>
            <select
              id="edit_role"
              value={formData.role}
              onChange={(e) => setFormData({ ...formData, role: e.target.value })}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-800 dark:text-white"
              required
            >
              <option value="user">Пользователь</option>
              <option value="admin">Администратор</option>
              <option value="superadmin">Суперадмин</option>
            </select>
          </div>
          <div className="flex justify-end gap-3">
            <Button type="button" onClick={editModal.closeModal} variant="secondary">
              Отмена
            </Button>
            <Button type="submit">Сохранить</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

