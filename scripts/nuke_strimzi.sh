#!/bin/bash
set -e

echo "💣 STARTING ROBUST CLEANUP..."

# 1. Uninstall Helm
echo "1. Uninstalling Helm release..."
helm uninstall strimzi-kafka-operator -n log-analytics --ignore-not-found --wait || true

# 2. Function to force delete resources
force_delete() {
    TYPE=$1
    NAME=$2
    NS=$3
    
    echo "   Targeting $TYPE $NAME..."
    # Run delete in background to speed up
    kubectl delete $TYPE $NAME -n $NS --ignore-not-found --grace-period=0 --force &
    
    # Wait loop
    count=0
    while kubectl get $TYPE $NAME -n $NS &> /dev/null; do
        echo "   Waiting for $NAME to vanish..."
        sleep 2
        count=$((count+1))
        if [ $count -gt 10 ]; then
             echo "   ⚠️ Stuck! Patching finalizer..."
             kubectl patch $TYPE $NAME -n $NS -p '{"metadata":{"finalizers":[]}}' --type=merge || true
        fi
    done
    echo "   ✅ Deleted $NAME"
}

# 3. Delete the specific stuck RoleBindings
echo "2. Deleting stuck RoleBindings..."
force_delete rolebinding strimzi-cluster-operator log-analytics
force_delete rolebinding strimzi-cluster-operator-entity-operator-delegation log-analytics
force_delete rolebinding strimzi-cluster-operator-watched log-analytics
force_delete rolebinding strimzi-cluster-operator-topic-operator-delegation log-analytics

# 4. Delete Cluster resources
echo "3. Deleting Cluster resources..."
kubectl delete clusterrolebinding strimzi-cluster-operator-namespaced --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-leader-election --ignore-not-found
kubectl delete clusterrolebinding strimzi-cluster-operator-global --ignore-not-found
kubectl delete clusterrole strimzi-cluster-operator-namespaced --ignore-not-found
kubectl delete clusterrole strimzi-cluster-operator-leader-election --ignore-not-found
kubectl delete clusterrole strimzi-cluster-operator-global --ignore-not-found

# 5. Delete CRDs
echo "4. Deleting CRDs..."
kubectl get crd | grep strimzi | awk '{print $1}' | xargs -r kubectl delete crd --ignore-not-found

echo "----------------------------------------"
echo "✨ Environment CLEAN. Installing Strimzi..."
echo "----------------------------------------"

helm upgrade --install strimzi-kafka-operator strimzi/strimzi-kafka-operator \
    --namespace log-analytics \
    --version 0.44.0 \
    --force \
    --set watchAnyNamespace=false \
    --set watchNamespaces="{log-analytics}"

echo "✅ SUCCESS! Strimzi installed."
