#!/bin/bash
echo "🔥 NUKING STRIMZI RESOURCES MANUALLY..."

# 1. Uninstall Helm Release
helm uninstall strimzi-kafka-operator -n log-analytics --ignore-not-found

# 2. Namespace level RoleBindings (The ones causing errors)
echo "Deleting RoleBindings..."
kubectl delete rolebinding strimzi-cluster-operator-watched -n log-analytics --ignore-not-found
kubectl delete rolebinding strimzi-cluster-operator-entity-operator-delegation -n log-analytics --ignore-not-found
kubectl delete rolebinding strimzi-cluster-operator -n log-analytics --ignore-not-found
kubectl delete rolebinding strimzi-cluster-operator-topic-operator-delegation -n log-analytics --ignore-not-found

# 3. Cluster level (Global)
echo "Deleting Cluster Resources..."
kubectl delete clusterrolebinding strimzi-cluster-operator-namespaced --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-leader-election --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-global --ignore-not-found

kubectl delete clusterrole strimzi-cluster-operator-namespaced --ignore-not-found
kubectl delete clusterrole strimzi-cluster-operator-leader-election --ignore-not-found
kubectl delete clusterrole strimzi-cluster-operator-global --ignore-not-found
kubectl delete clusterrole strimzi-kafka-broker --ignore-not-found
kubectl delete clusterrole strimzi-entity-operator --ignore-not-found
kubectl delete clusterrole strimzi-topic-operator --ignore-not-found

# 4. CRDs (Final cleanup)
echo "Deleting CRDs..."
kubectl get crd | grep strimzi | awk '{print $1}' | xargs kubectl delete crd

echo "✅ DONE. Environment is clean."
echo "👉 Now run: ./scripts/deploy-gke.sh"
